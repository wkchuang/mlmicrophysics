from mlmicrophysics.models import DenseNeuralNetwork
from mlmicrophysics.data import subset_data_files_by_date, assemble_data, output_quantile_curves
from sklearn.preprocessing import QuantileTransformer
from sklearn.metrics import r2_score
import pandas as pd
import numpy as np
import os
import argparse
import yaml
from os.path import exists, join
import pickle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="Path to config file")
    args = parser.parse_args()
    with open(args.config) as config_file:
        config = yaml.load(config_file, Loader=yaml.FullLoader)
    data_path = config["data"]["data_path"]
    out_path = config["data"]["out_path"]
    input_cols = config["data"]["input_cols"]
    output_cols = config["data"]["output_cols"]
    if "qc_thresh" not in config.keys():
        qc_thresh = 1e-6
    else:
        qc_thresh = config["data"]["qc_thresh"]
    input_scaler = QuantileTransformer(n_quantiles=config["data"]["n_quantiles"])
    output_scaler = QuantileTransformer(n_quantiles=config["data"]["n_quantiles"])
    scratch_path = config["data"]["scratch_path"]
    subsample = config["data"]["subsample"]
    np.random.seed(config["data"]["random_seed"])

    if not exists(out_path):
        os.makedirs(out_path)
    files = dict()
    files["train"], files["val"], files["test"] = subset_data_files_by_date(data_path, **config["data"]["subset_data"])
    subsets = ["train", "val", "test"]
    input_data = {}
    output_data = {}
    meta_data = {}
    input_quant_data = {}
    output_quant_data = {}
    print("Loading data")
    for subset in subsets:
        print(subset)
        input_data[subset], output_data[subset], meta_data[subset] = assemble_data(files[subset],
                                                                                   input_cols,
                                                                                   output_cols,
                                                                                   subsample=subsample,
                                                                                   qc_thresh=qc_thresh)
        if subset == "train":
            input_quant_data[subset] = pd.DataFrame(input_scaler.fit_transform(input_data[subset]), columns=input_cols)
            output_quant_data[subset] = pd.DataFrame(output_scaler.fit_transform(output_data[subset]), columns=output_cols)
        else:
            input_quant_data[subset] = pd.DataFrame(input_scaler.transform(input_data[subset]), columns=input_cols)
            output_quant_data[subset] = pd.DataFrame(output_scaler.transform(output_data[subset]), columns=output_cols)
    if "scratch_path" in config["data"].keys():
        if not exists(config["data"]["scratch_path"]):
            os.makedirs(config["data"]["scratch_path"])
        for subset in subsets:
            input_quant_data[subset].to_parquet(join(scratch_path, f"mp_quant_input_{subset}.parquet"))
            output_quant_data[subset].to_parquet(join(scratch_path, f"mp_quant_output_{subset}.parquet"))
            output_data[subset].to_parquet(join(scratch_path, f"mp_output_{subset}.parquet"))
            meta_data[subset].to_parquet(join(scratch_path, f"mp_meta_{subset}.parquet"))
    output_quantile_curves(input_scaler, input_cols, join(out_path, "input_quantile_scaler.nc"))
    output_quantile_curves(output_scaler, output_cols, join(out_path, "output_quantile_scaler.nc"))
    with open(join(out_path, "input_quantile_transform.pkl"), "wb") as in_quant_pickle:
        pickle.dump(input_scaler, in_quant_pickle)
    with open(join(out_path, "output_quantile_transform.pkl"), "wb") as out_quant_pickle:
        pickle.dump(output_scaler, out_quant_pickle)
    print("Training")
    emulator_nn = DenseNeuralNetwork(**config["model"])
    emulator_nn.fit(input_quant_data["train"], output_quant_data["train"],
                    xv=input_quant_data["val"], yv=output_quant_data["val"])
    emulator_nn.save_fortran_model(join(out_path, "quantile_neural_net_fortran.nc"))
    emulator_nn.model.save(join(out_path, "quantile_neural_net_keras.h5"))
    test_quant_preds = emulator_nn.predict(input_quant_data["test"], batch_size=40000)
    test_preds = output_scaler.inverse_transform(test_quant_preds)
    r2_test_scores = np.zeros(len(output_cols))
    for o, output_col in enumerate(output_cols):
        r2_test_scores[o] = r2_score(np.log10(output_data["test"][output_col].values),
                                     np.log10(test_preds[:, o]))
        print(output_col, r2_test_scores[o])

if __name__ == "__main__":
    main()
