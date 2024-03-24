# File that implements flask server

import os
import re
import json
import flask
import pickle
import pandas as pd
import numpy as np
import tensorflow as tf

# Define the path
prefix = '/opt/ml/'
model_path = os.path.join(prefix, 'model')

# Load the dictionaries
with open(os.path.join(model_path, "topics_vocab.pkl"), "rb") as f:
    target_vocab = pickle.load(f)
    
target_vocab_inv = {j:i for i,j in target_vocab.items()}

print("Loaded target vocab")

with open(os.path.join(model_path, "level_0_1_ids.pkl"), "rb") as f:
    level_0_1_ids = pickle.load(f)

print("Loaded level 0 and level 1 IDs")

with open(os.path.join(model_path, "doc_type_vocab.pkl"), "rb") as f:
    doc_vocab = pickle.load(f)
    
doc_vocab_inv = {j:i for i,j in doc_vocab.items()}

print("Loaded doc_type vocab")

with open(os.path.join(model_path, "journal_name_vocab.pkl"), "rb") as f:
    journal_vocab = pickle.load(f)
    
journal_vocab_inv = {j:i for i,j in journal_vocab.items()}

print("Loaded journal vocab")

with open(os.path.join(model_path, "paper_title_vocab.pkl"), "rb") as f:
    title_vocab = pickle.load(f)
    
title_vocab_inv = {j:i for i,j in title_vocab.items()}

print("Loaded title vocab")

with open(os.path.join(model_path, "tag_id_vocab.pkl"), "rb") as f:
    tag_id_vocab = pickle.load(f)

print("Loaded tag ID vocab")

with open(os.path.join(model_path, "ancestor_chains.pkl"), "rb") as f:
    ancestors = pickle.load(f)

print("Loaded ancestor chains")

encoding_layer = tf.keras.layers.experimental.preprocessing.CategoryEncoding(
    max_tokens=len(target_vocab)+1, output_mode="binary", sparse=False)

# Load the model components
raw_model = tf.keras.models.load_model(os.path.join(model_path, 'mag_model_V3'), compile=False)
raw_model.trainable = False

print("Loaded raw model")

mag_model = tf.keras.Model(inputs=raw_model.inputs, 
                           outputs=tf.math.top_k(raw_model.outputs, k=250))
mag_model.trainable = False

for layer in mag_model.layers:
    if isinstance(layer, tf.keras.layers.Dropout) and hasattr(layer, 'rate'):
        layer.rate = 0.0

print("Created full model")

def invert_abstract_to_abstract(invert_abstract):
    invert_abstract = json.loads(invert_abstract)
    ab_len = invert_abstract['IndexLength']
    
    if 30 < ab_len < 1000:
        abstract = [" "]*ab_len
        for key, value in invert_abstract['InvertedIndex'].items():
            for i in value:
                abstract[i] = key
        final_abstract = " ".join(abstract)
    else:
        final_abstract = None
    return final_abstract

def clean_abstract(abstract, inverted=True):
    if inverted:
        if abstract:
            abstract = invert_abstract_to_abstract(abstract)
        else:
            pass
    else:
        pass
    abstract = clean_text(abstract)
    return abstract

def clean_text(text):
    try:
        text = text.lower()

        text = re.sub('[^a-zA-Z0-9 ]+', ' ', text)
        text = re.sub(' +', ' ', text)
        text = text.strip()
        
    except:
        text = ""
    return text

def try_lowercase(text):
    try:
        text = text.lower()
    except:
        pass
    return text

def tokenize_feature(feature, feature_name='doc_type'):
    if feature_name=='doc_type':
        vocab = doc_vocab
    else:
        vocab = journal_vocab
    unk_token_id = vocab.get('[UNK]')
    none_token_id = vocab.get('[NONE]')
    if feature:
        token_feature = [vocab.get(feature, unk_token_id)]
    else:
        token_feature = [none_token_id]
    return token_feature

def tokenize_title(feature):
    split_feature = feature.split(" ")
    vocab = title_vocab
    unk_token_id = vocab.get('[UNK]')
    none_token_id = vocab.get('[NONE]')
    if feature:
        token_feature = [vocab.get(x, unk_token_id) for x in split_feature]
    else:
        token_feature = [none_token_id]
    return token_feature

def cut_length(data, seq_len=512):
    return data[:seq_len]

# The flask app for serving predictions
app = flask.Flask(__name__)
@app.route('/ping', methods=['GET'])
def ping():
    # Check if the classifier was loaded correctly
    try:
        _ = mag_model.get_layer('cls')
        status = 200
    except:
        status = 400
    return flask.Response(response= json.dumps(' '), status=status, mimetype='application/json' )

@app.route('/invocations', methods=['POST'])
def transformation():
    # Get input JSON data and convert it to a DF
    input_json = flask.request.get_json()
    input_json = json.dumps(input_json)
    input_df = pd.read_json(input_json, orient='records').reset_index()

    # Tokenize data
    input_df['title'] = input_df['title'].apply(clean_text)
    input_df['abstract'] = input_df.apply(lambda x: clean_abstract(x.abstract, x.inverted_abstract), axis=1)
    input_df['journal'] = input_df['journal'].apply(try_lowercase)
    input_df['paper_title_tok'] = input_df['title'].apply(tokenize_title)
    input_df['abstract_tok'] = input_df['abstract'].apply(tokenize_title)
    input_df['doc_type_tok'] = input_df['doc_type'].apply(tokenize_feature, args=('doc_type',))
    input_df['journal_tok'] = input_df['journal'].apply(tokenize_feature, args=('journal',))
    
    input_df['paper_title_tok'] = input_df['paper_title_tok'].apply(cut_length, args=(32,))
    input_df['abstract_tok'] = input_df['abstract_tok'].apply(cut_length, args=(256,))
    paper_ids = input_df['paper_id'].tolist()
    
    paper_titles = tf.ragged.constant(input_df['paper_title_tok'].to_list()).to_tensor(shape=[None, 32])
    abstracts = tf.ragged.constant(input_df['abstract_tok'].to_list()).to_tensor(shape=[None, 256])
    
    doc_types = tf.convert_to_tensor(input_df['doc_type_tok'].to_list())
    journal = tf.convert_to_tensor(input_df['journal_tok'].to_list())
    
    # Predict
    model_output = mag_model([paper_titles, abstracts, doc_types, journal])
    
    scores = model_output.values.numpy()[0].tolist()
    preds = model_output.indices.numpy()[0].tolist()

    # Transform predicted labels into tags (to get most likely concepts)
    all_tags = []
    for score, pred, paper_id in zip(scores, preds, paper_ids):
        pred_score_dict = {pred_i:score_j for pred_i,score_j in zip(pred,score)}
        tags = []
        tag_scores = []
        tag_ids = []
        pred_ids = []
        
        for i in range(20):
            if (pred[i] in level_0_1_ids) & (score[i] >= 0.32):
                tags.append(target_vocab_inv.get(pred[i]))
                tag_scores.append(score[i])
                tag_ids.append(tag_id_vocab.get(pred[i]))
                pred_ids.append(pred[i])
            elif score[i] >= 0.41:
                tags.append(target_vocab_inv.get(pred[i]))
                tag_scores.append(score[i])
                tag_ids.append(tag_id_vocab.get(pred[i]))
                pred_ids.append(pred[i])
            else:
                pass
        if len(tags) == 0:
            tags.append(target_vocab_inv.get(pred[0]))
            tag_scores.append(score[0])
            tag_ids.append(tag_id_vocab.get(pred[0]))
            pred_ids.append(pred[0])
    
        # The following code makes sure that every concept has a path (chain) up to an L0
        chain_ids = []
        pred_ancestors_chains_dict = {pred_id:ancestors[pred_id] for pred_id in pred_ids}
        for pred_id in pred_ids:
            all_ancestor_id_chains = pred_ancestors_chains_dict[pred_id]['anc_ids']
            all_ancestor_name_chains = pred_ancestors_chains_dict[pred_id]['anc_tags']

            if pred_id in chain_ids:
                # if pred was already part of a chain, pass
                pass
            else:
                if all_ancestor_id_chains:
                    if len(all_ancestor_id_chains) == 1:
                        chain_ids += all_ancestor_id_chains[0]
                    else:
                        # get the score for each chain
                        chain_scores = []
                        for chain in all_ancestor_id_chains:
                            chain_scores.append(np.sum([pred_score_dict.get(x, 0.0) for x in chain]))
                        chain_ids += all_ancestor_id_chains[np.argmax(np.asarray(chain_scores))]
                else:
                    # passing in the case that there are no ancestors (level 0 concepts)
                    pass

        chain_ids = list(set(chain_ids))

        added_tags = [x for x in chain_ids if x not in pred_ids]
        
        for added_tag in added_tags:
            tags.append(target_vocab_inv.get(added_tag))
            tag_scores.append(pred_score_dict.get(added_tag, 0.0))
            tag_ids.append(tag_id_vocab.get(added_tag))
            
        all_tags.append({
            "paper_id": paper_id,
            "tags": tags,
            "scores": tag_scores,
            "tag_ids": tag_ids,
            "chain": pred_ancestors_chains_dict
        })

    # Transform predictions to JSON
    result = json.dumps(all_tags)
    return flask.Response(response=result, status=200, mimetype='application/json')
