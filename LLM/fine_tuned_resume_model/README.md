---
tags:
- sentence-transformers
- sentence-similarity
- feature-extraction
- dense
- generated_from_trainer
- dataset_size:100
- loss:CosineSimilarityLoss
base_model: sentence-transformers/all-MiniLM-L6-v2
widget:
- source_sentence: 'Graphic Designer

    Summary: Professional with hands-on experience across the domain.

    Skills: adobe cc, assets, branding, illustration, layout, typography.

    Highlights: Delivered projects end-to-end; worked cross-functionally; documented
    results. Passion for continuous learning.'
  sentences:
  - 'UX/UI Designer

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with prototyping, usability testing, user research, wireframing.
    Focus on quality, reliability, and impact.'
  - 'Mobile Engineer (iOS/Android)

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with android, app store, kotlin, mobile, swift, ui. Focus
    on quality, reliability, and impact.'
  - 'Graphic Designer

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with adobe cc, branding, illustration, layout, typography.
    Focus on quality, reliability, and impact.'
- source_sentence: 'Sales Representative

    Summary: Professional with hands-on experience across the domain.

    Skills: cold calling, crm, negotiation, pipeline, prospecting, quota.

    Highlights: Delivered projects end-to-end; worked cross-functionally; documented
    results. Focus on quality, reliability, and impact.'
  sentences:
  - 'SRE

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with automation, incident response, kubernetes, linux,
    observability, slo. Experience in fast-paced environments.'
  - 'Product Manager (SaaS)

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with agile, prioritization, roadmap, stakeholders, user
    research. Experience in fast-paced environments.'
  - 'Sales Development Rep (SDR)

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with crm, outbound, pipeline, prospecting, quota. Focus
    on quality, reliability, and impact.'
- source_sentence: 'Data Scientist

    Summary: Professional with hands-on experience across the domain.

    Skills: experimentation, ml, nlp, numpy, pandas, python, sklearn, statistics,
    visualization.

    Highlights: Delivered projects end-to-end; worked cross-functionally; documented
    results. Focus on quality, reliability, and impact.'
  sentences:
  - 'ML Engineer (Platform)

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with deployment, feature store, inference, mlops, python,
    pytorch, tensorflow. Passion for continuous learning.'
  - 'Frontend Engineer (React)

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with accessibility, css, html, react, testing, typescript,
    ui. Demonstrated problem-solving and ownership.'
  - 'Data Scientist (Product)

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with dashboards, experimentation, ml, numpy, pandas,
    python, statistics. Strong collaboration and communication.'
- source_sentence: 'Attorney

    Summary: Professional with hands-on experience across the domain.

    Skills: compliance, contracts, legal research, litigation, negotiation, writing.

    Highlights: Delivered projects end-to-end; worked cross-functionally; documented
    results. Focus on quality, reliability, and impact.'
  sentences:
  - 'Teacher (K-12)

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with assessment, classroom management, curriculum, lesson
    planning. Demonstrated problem-solving and ownership.'
  - 'Attorney (Corporate)

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with compliance, contracts, drafting, legal research,
    negotiation. Experience in fast-paced environments.'
  - 'Backend Software Engineer

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with apis, c++, cloud, docker, java, linux, microservices,
    python. Demonstrated problem-solving and ownership.'
- source_sentence: 'Software Backend Engineer

    Summary: Professional with hands-on experience across the domain.

    Skills: c++, cloud, docker, java, linux, microservices, python, rest, sql.

    Highlights: Delivered projects end-to-end; worked cross-functionally; documented
    results. Demonstrated problem-solving and ownership.'
  sentences:
  - 'ML Engineer (Platform)

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with deployment, feature store, inference, python, pytorch,
    tensorflow. Focus on quality, reliability, and impact.'
  - 'Frontend Engineer (React)

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with accessibility, css, html, react, testing, typescript,
    ui. Passion for continuous learning.'
  - 'Backend Software Engineer

    Responsibilities: Contribute across the team and deliver high-quality outcomes.

    Requirements: experience with apis, c++, cloud, docker, java, microservices, python,
    sql. Strong collaboration and communication.'
pipeline_tag: sentence-similarity
library_name: sentence-transformers
metrics:
- pearson_cosine
- spearman_cosine
model-index:
- name: SentenceTransformer based on sentence-transformers/all-MiniLM-L6-v2
  results:
  - task:
      type: semantic-similarity
      name: Semantic Similarity
    dataset:
      name: resume job val
      type: resume-job-val
    metrics:
    - type: pearson_cosine
      value: 0.9522756507595216
      name: Pearson Cosine
    - type: spearman_cosine
      value: 0.8660254037844387
      name: Spearman Cosine
---

# SentenceTransformer based on sentence-transformers/all-MiniLM-L6-v2

This is a [sentence-transformers](https://www.SBERT.net) model finetuned from [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2). It maps sentences & paragraphs to a 384-dimensional dense vector space and can be used for semantic textual similarity, semantic search, paraphrase mining, text classification, clustering, and more.

## Model Details

### Model Description
- **Model Type:** Sentence Transformer
- **Base model:** [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) <!-- at revision c9745ed1d9f207416be6d2e6f8de32d1f16199bf -->
- **Maximum Sequence Length:** 256 tokens
- **Output Dimensionality:** 384 dimensions
- **Similarity Function:** Cosine Similarity
<!-- - **Training Dataset:** Unknown -->
<!-- - **Language:** Unknown -->
<!-- - **License:** Unknown -->

### Model Sources

- **Documentation:** [Sentence Transformers Documentation](https://sbert.net)
- **Repository:** [Sentence Transformers on GitHub](https://github.com/UKPLab/sentence-transformers)
- **Hugging Face:** [Sentence Transformers on Hugging Face](https://huggingface.co/models?library=sentence-transformers)

### Full Model Architecture

```
SentenceTransformer(
  (0): Transformer({'max_seq_length': 256, 'do_lower_case': False, 'architecture': 'BertModel'})
  (1): Pooling({'word_embedding_dimension': 384, 'pooling_mode_cls_token': False, 'pooling_mode_mean_tokens': True, 'pooling_mode_max_tokens': False, 'pooling_mode_mean_sqrt_len_tokens': False, 'pooling_mode_weightedmean_tokens': False, 'pooling_mode_lasttoken': False, 'include_prompt': True})
  (2): Normalize()
)
```

## Usage

### Direct Usage (Sentence Transformers)

First install the Sentence Transformers library:

```bash
pip install -U sentence-transformers
```

Then you can load this model and run inference.
```python
from sentence_transformers import SentenceTransformer

# Download from the 🤗 Hub
model = SentenceTransformer("sentence_transformers_model_id")
# Run inference
sentences = [
    'Software Backend Engineer\nSummary: Professional with hands-on experience across the domain.\nSkills: c++, cloud, docker, java, linux, microservices, python, rest, sql.\nHighlights: Delivered projects end-to-end; worked cross-functionally; documented results. Demonstrated problem-solving and ownership.',
    'Backend Software Engineer\nResponsibilities: Contribute across the team and deliver high-quality outcomes.\nRequirements: experience with apis, c++, cloud, docker, java, microservices, python, sql. Strong collaboration and communication.',
    'Frontend Engineer (React)\nResponsibilities: Contribute across the team and deliver high-quality outcomes.\nRequirements: experience with accessibility, css, html, react, testing, typescript, ui. Passion for continuous learning.',
]
embeddings = model.encode(sentences)
print(embeddings.shape)
# [3, 384]

# Get the similarity scores for the embeddings
similarities = model.similarity(embeddings, embeddings)
print(similarities)
# tensor([[1.0000, 0.8173, 0.5277],
#         [0.8173, 1.0000, 0.6495],
#         [0.5277, 0.6495, 1.0000]])
```

<!--
### Direct Usage (Transformers)

<details><summary>Click to see the direct usage in Transformers</summary>

</details>
-->

<!--
### Downstream Usage (Sentence Transformers)

You can finetune this model on your own dataset.

<details><summary>Click to expand</summary>

</details>
-->

<!--
### Out-of-Scope Use

*List how the model may foreseeably be misused and address what users ought not to do with the model.*
-->

## Evaluation

### Metrics

#### Semantic Similarity

* Dataset: `resume-job-val`
* Evaluated with [<code>EmbeddingSimilarityEvaluator</code>](https://sbert.net/docs/package_reference/sentence_transformer/evaluation.html#sentence_transformers.evaluation.EmbeddingSimilarityEvaluator)

| Metric              | Value     |
|:--------------------|:----------|
| pearson_cosine      | 0.9523    |
| **spearman_cosine** | **0.866** |

<!--
## Bias, Risks and Limitations

*What are the known or foreseeable issues stemming from this model? You could also flag here known failure cases or weaknesses of the model.*
-->

<!--
### Recommendations

*What are recommendations with respect to the foreseeable issues? For example, filtering explicit content.*
-->

## Training Details

### Training Dataset

#### Unnamed Dataset

* Size: 100 training samples
* Columns: <code>sentence_0</code>, <code>sentence_1</code>, and <code>label</code>
* Approximate statistics based on the first 100 samples:
  |         | sentence_0                                                                        | sentence_1                                                                         | label                                                         |
  |:--------|:----------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------|:--------------------------------------------------------------|
  | type    | string                                                                            | string                                                                             | float                                                         |
  | details | <ul><li>min: 54 tokens</li><li>mean: 62.1 tokens</li><li>max: 71 tokens</li></ul> | <ul><li>min: 36 tokens</li><li>mean: 44.63 tokens</li><li>max: 53 tokens</li></ul> | <ul><li>min: 0.0</li><li>mean: 0.5</li><li>max: 1.0</li></ul> |
* Samples:
  | sentence_0                                                                                                                                                                                                                                                                                                                          | sentence_1                                                                                                                                                                                                                                               | label            |
  |:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------------|
  | <code>UX/UI Designer<br>Summary: Professional with hands-on experience across the domain.<br>Skills: design systems, figma, prototyping, usability testing, user research, wireframing.<br>Highlights: Delivered projects end-to-end; worked cross-functionally; documented results. Strong collaboration and communication.</code> | <code>UX/UI Designer<br>Responsibilities: Contribute across the team and deliver high-quality outcomes.<br>Requirements: experience with figma, prototyping, usability testing, wireframing. Experience in fast-paced environments.</code>               | <code>1.0</code> |
  | <code>Mobile App Developer<br>Summary: Professional with hands-on experience across the domain.<br>Skills: android, ios, kotlin, mobile, push notifications, rest, swift, ui.<br>Highlights: Delivered projects end-to-end; worked cross-functionally; documented results. Demonstrated problem-solving and ownership.</code>       | <code>Mobile Engineer (iOS/Android)<br>Responsibilities: Contribute across the team and deliver high-quality outcomes.<br>Requirements: experience with android, app store, kotlin, mobile, swift, ui. Focus on quality, reliability, and impact.</code> | <code>1.0</code> |
  | <code>Customer Support Specialist<br>Summary: Professional with hands-on experience across the domain.<br>Skills: communication, knowledge base, sla, tickets, troubleshooting.<br>Highlights: Delivered projects end-to-end; worked cross-functionally; documented results. Strong collaboration and communication.</code>         | <code>Customer Support Specialist<br>Responsibilities: Contribute across the team and deliver high-quality outcomes.<br>Requirements: experience with communication, sla, tickets, troubleshooting. Focus on quality, reliability, and impact.</code>    | <code>1.0</code> |
* Loss: [<code>CosineSimilarityLoss</code>](https://sbert.net/docs/package_reference/sentence_transformer/losses.html#cosinesimilarityloss) with these parameters:
  ```json
  {
      "loss_fct": "torch.nn.modules.loss.MSELoss"
  }
  ```

### Training Hyperparameters
#### Non-Default Hyperparameters

- `eval_strategy`: steps
- `per_device_train_batch_size`: 16
- `per_device_eval_batch_size`: 16
- `multi_dataset_batch_sampler`: round_robin

#### All Hyperparameters
<details><summary>Click to expand</summary>

- `overwrite_output_dir`: False
- `do_predict`: False
- `eval_strategy`: steps
- `prediction_loss_only`: True
- `per_device_train_batch_size`: 16
- `per_device_eval_batch_size`: 16
- `per_gpu_train_batch_size`: None
- `per_gpu_eval_batch_size`: None
- `gradient_accumulation_steps`: 1
- `eval_accumulation_steps`: None
- `torch_empty_cache_steps`: None
- `learning_rate`: 5e-05
- `weight_decay`: 0.0
- `adam_beta1`: 0.9
- `adam_beta2`: 0.999
- `adam_epsilon`: 1e-08
- `max_grad_norm`: 1
- `num_train_epochs`: 3
- `max_steps`: -1
- `lr_scheduler_type`: linear
- `lr_scheduler_kwargs`: {}
- `warmup_ratio`: 0.0
- `warmup_steps`: 0
- `log_level`: passive
- `log_level_replica`: warning
- `log_on_each_node`: True
- `logging_nan_inf_filter`: True
- `save_safetensors`: True
- `save_on_each_node`: False
- `save_only_model`: False
- `restore_callback_states_from_checkpoint`: False
- `no_cuda`: False
- `use_cpu`: False
- `use_mps_device`: False
- `seed`: 42
- `data_seed`: None
- `jit_mode_eval`: False
- `use_ipex`: False
- `bf16`: False
- `fp16`: False
- `fp16_opt_level`: O1
- `half_precision_backend`: auto
- `bf16_full_eval`: False
- `fp16_full_eval`: False
- `tf32`: None
- `local_rank`: 0
- `ddp_backend`: None
- `tpu_num_cores`: None
- `tpu_metrics_debug`: False
- `debug`: []
- `dataloader_drop_last`: False
- `dataloader_num_workers`: 0
- `dataloader_prefetch_factor`: None
- `past_index`: -1
- `disable_tqdm`: False
- `remove_unused_columns`: True
- `label_names`: None
- `load_best_model_at_end`: False
- `ignore_data_skip`: False
- `fsdp`: []
- `fsdp_min_num_params`: 0
- `fsdp_config`: {'min_num_params': 0, 'xla': False, 'xla_fsdp_v2': False, 'xla_fsdp_grad_ckpt': False}
- `fsdp_transformer_layer_cls_to_wrap`: None
- `accelerator_config`: {'split_batches': False, 'dispatch_batches': None, 'even_batches': True, 'use_seedable_sampler': True, 'non_blocking': False, 'gradient_accumulation_kwargs': None}
- `deepspeed`: None
- `label_smoothing_factor`: 0.0
- `optim`: adamw_torch
- `optim_args`: None
- `adafactor`: False
- `group_by_length`: False
- `length_column_name`: length
- `ddp_find_unused_parameters`: None
- `ddp_bucket_cap_mb`: None
- `ddp_broadcast_buffers`: False
- `dataloader_pin_memory`: True
- `dataloader_persistent_workers`: False
- `skip_memory_metrics`: True
- `use_legacy_prediction_loop`: False
- `push_to_hub`: False
- `resume_from_checkpoint`: None
- `hub_model_id`: None
- `hub_strategy`: every_save
- `hub_private_repo`: None
- `hub_always_push`: False
- `gradient_checkpointing`: False
- `gradient_checkpointing_kwargs`: None
- `include_inputs_for_metrics`: False
- `include_for_metrics`: []
- `eval_do_concat_batches`: True
- `fp16_backend`: auto
- `push_to_hub_model_id`: None
- `push_to_hub_organization`: None
- `mp_parameters`: 
- `auto_find_batch_size`: False
- `full_determinism`: False
- `torchdynamo`: None
- `ray_scope`: last
- `ddp_timeout`: 1800
- `torch_compile`: False
- `torch_compile_backend`: None
- `torch_compile_mode`: None
- `dispatch_batches`: None
- `split_batches`: None
- `include_tokens_per_second`: False
- `include_num_input_tokens_seen`: False
- `neftune_noise_alpha`: None
- `optim_target_modules`: None
- `batch_eval_metrics`: False
- `eval_on_start`: False
- `use_liger_kernel`: False
- `eval_use_gather_object`: False
- `average_tokens_across_devices`: False
- `prompts`: None
- `batch_sampler`: batch_sampler
- `multi_dataset_batch_sampler`: round_robin
- `router_mapping`: {}
- `learning_rate_mapping`: {}

</details>

### Training Logs
| Epoch | Step | resume-job-val_spearman_cosine |
|:-----:|:----:|:------------------------------:|
| 1.0   | 7    | 0.8660                         |


### Framework Versions
- Python: 3.10.6
- Sentence Transformers: 5.1.0
- Transformers: 4.48.3
- PyTorch: 2.7.1+cpu
- Accelerate: 1.10.1
- Datasets: 4.0.0
- Tokenizers: 0.21.0

## Citation

### BibTeX

#### Sentence Transformers
```bibtex
@inproceedings{reimers-2019-sentence-bert,
    title = "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks",
    author = "Reimers, Nils and Gurevych, Iryna",
    booktitle = "Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing",
    month = "11",
    year = "2019",
    publisher = "Association for Computational Linguistics",
    url = "https://arxiv.org/abs/1908.10084",
}
```

<!--
## Glossary

*Clearly define terms in order to be accessible across audiences.*
-->

<!--
## Model Card Authors

*Lists the people who create the model card, providing recognition and accountability for the detailed work that goes into its construction.*
-->

<!--
## Model Card Contact

*Provides a way for people who have updates to the Model Card, suggestions, or questions, to contact the Model Card authors.*
-->