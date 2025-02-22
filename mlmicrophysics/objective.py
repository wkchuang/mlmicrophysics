from echo.src.base_objective import BaseObjective
import numpy as np
from mlmicrophysics.models import DenseNeuralNetwork
import pandas as pd
from os.path import join
import pickle
from sklearn.metrics import r2_score


class Objective(BaseObjective):
    def __init__(self, config, metric="val_loss"):
        BaseObjective.__init__(self, config, metric)

    def train(self, trial, conf):
        input_quant_data = {}
        output_quant_data = {}
        output_data = {}
        subsets = ["train", "val"]
        for subset in subsets:
            input_quant_data[subset] = pd.read_parquet(join(conf["data"]["scratch_path"],
                                                            f"mp_quant_input_{subset}.parquet"))
            output_quant_data[subset] = pd.read_parquet(join(conf["data"]["scratch_path"],
                                                             f"mp_quant_output_{subset}.parquet"))
            output_data[subset] = pd.read_parquet(join(conf["data"]["scratch_path"], f"mp_output_{subset}.parquet"))
        with open(join(conf["data"]["out_path"], "output_quantile_transform.pkl"), "rb") as out_scaler_pickle:
            output_scaler = pickle.load(out_scaler_pickle)
        dnn = DenseNeuralNetwork(**conf["model"])
        dnn.fit(input_quant_data["train"], output_quant_data["train"])
        val_quant_preds = dnn.predict(input_quant_data["val"], batch_size=40000)
        val_preds = output_scaler.inverse_transform(val_quant_preds)
        val_r2 = r2_score(np.log10(output_data["val"]), np.log10(val_preds))
        results_dict = {"val_loss": val_r2}
        return results_dict
