# Parameters written as none will be automatically set in the code, and all properties can be modified through command line parameters.
# e.g. --dict_mult 2
cfg = {
        ## global
        "seed": 49,
        'device_list': '1,2,3,4,5,6',
        "extractor": 'conceptx', # choose from ["ae", "tcav"]
        "model_to_interpret": "pythia-70m", # choose from ["llama-2-7b-chat", "pythia-70m"]
        "load_path": "./best_reconstruct",#"{The path where you save checkpoints, e.g. /user/data/outputs/AE/best_reconstruct}",
        "load_extractor": False,
        

        ## AutoEncoder
        "dict_mult": 8,
        "d_mlp": None,
        "d_model": None,
        "val_freq": 100,
        "data_dir": "./data", #"{The directory where you save datasets, e.g. /user/data/datasets/pile/}",
        "dataset_name": "pile-tokenized-10b", #"{The training dataset name, e.g. pile-tokenized-10b}",
        "output_dir": "./output", #"{The directory where you save checkpoints, e.g. /user/data/outputs/AE}",
        "model_dir": "Pythia-70m", #"{The directory where you save your model, e.g. /user/data/models/Pythia-70m}",
        "reinit": 1,
        'init_type': 'kaiming_uniform',
        'remove_parallel': 1,
        'tied_enc_dec': 0,
        "epoch": 1,

        ## ConceptX
        "ConceptX_max_token": 5000,
        "ConceptX_clusters": 10,
        
        ## Training
        "num_batches": None,
        "device": "cuda:0",
        "batch_size": 8192,
        "l1_coeff": 0.5,
        "n_devices": 1, # For a relatively large model that requires multiple GPUs to load, load it onto 'n_devices' GPUs starting from 'device'.
        
        ## Concept Evaluating
        'evaluator': 'itc',
        'concept_eval_batchsize': 128,
        'return_type': 'weighted',
        
        ## Metric Evaluating
        'metric_evaluator': 'rc',
        'metric_eval_batchsize': 128 * 5,
        
        ## Buffer in AE_Dataloader
        "buffer_size": None,
        "buffer_mult": 400,
        "act_size": None,
        "buffer_batches": None,
        "model_batch_size":64,
        
        ## dataset
        "num_tokens": int(1363348000), # How many tokens do you want to use for training
        "seq_len": 128,
        "tokenized":True, # Whether the training data has been tokenized
        "data_from_hf":True, # Whether the dataset is downloaded from huggingface
        
        
        
        ## Which layer and part of the model should be explained?
        "layer": 0,
        "site": "resid_post",
        "layer_type": None,
        'name_only': 0,
        
        ## optimizer
        "beta1": 0.9,
        "beta2": 0.99,
        "lr": 0.001,
        
        ## spine
        "noise_level":0.2,
        "sparsity":0.85,
        
        ## convex optim
        "freq_sample_range": int(1e2),
        "reg": 0.3,
        
        ## intrinsic probing
        "language": "eng",
        "embedding": "bert",     # bert/fasttext
        "trainer": "map",        # map/mle
        "attribute": None,
        "diagonalize": False,
        "max_iter": 5,
        "show_charts":False,
        "selection_criterion": "log_likelihood", # accuracy / log_likelihood / mi
        'log_wandb': False, # to use wandb
}