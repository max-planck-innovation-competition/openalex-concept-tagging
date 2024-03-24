# openalex-concept-tagging

This repository contains all of the code for getting the [OpenAlex](https://openalex.org) concept tagger up and running. Go into the model iteration directory (V1 or V2) to find a more detailed explanation of how to use this repository. To learn more about concepts in OpenAlex, check out [the docs](https://docs.openalex.org/about-the-data/concept). 

### Model Iterations
* V1 (no longer used)
* V2 (no longer used)
* V3 (currently used)

Both a V1 and a V2 model were created but as of right now, the V3 model is being used in OpenAlex. Initially, abstract data was not available for the model so we went with a V1 model that only looked at paper titles and a few other features. Once paper abstract data became available, a V2 model was created and we saw a substantial increase in performance. In order to meet the needs for some of our users, a V3 model was created which used the same base tagging model that was developed for V2 but added additional logic for assigning parent concepts so that all concepts would have a path to the top of our concept tree/graph. For more information, please read the information at the top of the V3 directory.

### Model Development
You can find an explanation of the modeling and deployment process at the following link:
[OpenAlex: End-to-End Process for Concept Tagging](https://docs.google.com/document/d/1q3jBlEexskCZaSafFDMEEY3naTeyd7GS/edit?usp=sharing&ouid=112616748913247881031&rtpof=true&sd=true)

### Concepts
Input can be tagged with one or more of about 65,000 concepts, [listed here](https://docs.google.com/spreadsheets/d/1LBFHjPt4rj_9r0t0TTAlT68NwOtNH8Z21lBMsJDMoZg/edit?usp=sharing). Concepts are part of a hierarchical tree, with levels 0 (e.g., Mathematics) through 5 (e.g., Generalized inverse Gaussian distribution).

### Internal Usage

Run these following commands in the root directory of the repository to get the model up and running locally in a Docker Container. 

Configure AWS
```shell
aws configure
```

Download model artifacts
```shell
aws s3 cp s3://openalex-concept-tagger-model-files/ . --recursive
```

Copy the files to the appropriate directory
```shell
mkdir /V3/003_Deploy/model_to_api/container/model

cp ./V3/tag_id_vocab.pkl ./V3/003_Deploy/model_to_api/container/model/tag_id_vocab.pkl
cp ./V3/topics_vocab.pkl ./V3/003_Deploy/model_to_api/container/model/topics_vocab.pkl
cp ./V3/ancestor_chains.pkl ./V3/003_Deploy/model_to_api/container/model/ancestor_chains.pkl
cp ./V3/doc_type_vocab.pkl ./V3/003_Deploy/model_to_api/container/model/doc_type_vocab.pkl
cp ./V3/journal_name_vocab.pkl ./V3/003_Deploy/model_to_api/container/model/journal_name_vocab.pkl
cp ./V3/level_0_1_ids.pkl ./V3/003_Deploy/model_to_api/container/model/level_0_1_ids.pkl
cp ./V3/paper_title_vocab.pkl ./V3/003_Deploy/model_to_api/container/model/paper_title_vocab.pkl

mkdir /V3/003_Deploy/model_to_api/container/model/mag_model_V3

cp ./V3/model ./V3/003_Deploy/model_to_api/container/model/mag_model_V3
```

Change the file path to the model in the predictor.py file
```shell
# replace mag_model_V2 with mag_model_V3
sed -i 's/mag_model_V2/mag_model_V3/g' ./V3/003_Deploy/model_to_api/container/mag_model/predictor.py
```  

Build Docker Container
```shell
docker build ./V3/003_Deploy/model_to_api/container -t openalex-concept-tagger -f ./V3/003_Deploy/model_to_api/container/Dockerfile
```

Run Docker Container
```shell
docker run -p 8888:8080 openalex-concept-tagger
```

### Env Variables

```
# The amount of workers that will be used to serve the model
MODEL_SERVER_WORKERS=1
```
