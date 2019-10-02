from math import nan
from typing import Dict, List, Tuple, Union, Optional

from keras import Model
from keras.callbacks import Callback

PredictionsForOneEpoch = Dict[str, list]


class AdditionalValidationSets(Callback):
    def __init__(self, validation_sets, verbose=0, batch_size=None, record_original_history=True,
                 record_predictions=False):
        """
        :param validation_sets:
        a list of
        2-tuples ((validation_generator, validation_steps), validation_set_name) or
        3-tuples (validation_data, validation_targets, validation_set_name) or
        4-tuples (validation_data, validation_targets, sample_weights, validation_set_name)
        :param verbose:
        verbosity mode, 1 or 0
        :param batch_size:
        batch size to be used when evaluating on the additional datasets
        """
        super(AdditionalValidationSets, self).__init__()
        self.record_predictions = record_predictions
        self.validation_sets = validation_sets
        for validation_set in self.validation_sets:
            if len(validation_set) not in [2, 3, 4]:
                raise ValueError()
        self.epoch = []
        self.history: Dict[str, List[Union[float, PredictionsForOneEpoch]]] = {}
        self.verbose = verbose
        self.batch_size = batch_size
        self.record_original_history = record_original_history

    def on_train_begin(self, logs=None):
        self.epoch = []
        self.history = {}

    def on_epoch_end(self, epoch, logs=None):
        self.epoch.append(epoch)

        if self.record_original_history:
            # record the same values as History() as well
            logs = logs or {}
            for k, v in logs.items():
                self.history.setdefault(k, []).append(v)

        if len(self.validation_sets) == 0:
            return

        # evaluate on the additional validation sets
        model: Model = self.model_to_evaluate()

        for validation_set in self.validation_sets:
            (validation_generator, validation_steps) = None, None
            validation_data = None
            if len(validation_set) == 2:
                (validation_generator, validation_steps), validation_set_name = validation_set
                validation_targets = None
                sample_weights = None
            elif len(validation_set) == 3:
                validation_data, validation_targets, validation_set_name = validation_set
                sample_weights = None
            elif len(validation_set) == 4:
                validation_data, validation_targets, sample_weights, validation_set_name = validation_set
            else:
                raise ValueError()

            predictions = None
            if model is not None:
                if validation_generator is not None:  # this validation set is a generator
                    results = model.evaluate_generator(validation_generator,
                                                       validation_steps)
                    if self.record_predictions:
                        predictions = {
                            'y_pred': [],
                            'y_true': [],
                        }
                        for _ in range(validation_steps):
                            batch = next(validation_generator)
                            xs = batch[0]
                            ys = batch[1]
                            # TODO: I do not like that we have to call both .evaluate AND .predict with the same data if we want to do this
                            y_pred = model.predict(xs, batch_size=xs[0].shape[0])
                            predictions['y_pred'].append(y_pred)
                            predictions['y_true'].append(ys)
                        reformatted_predictions = {
                            'y_pred': [],
                            'y_true': [],
                        }
                        for batch in predictions['y_pred']:
                            for batch_idx in range(batch[0].shape[0]):
                                reformatted_predictions['y_pred'].append([output[batch_idx] for output in batch])
                        for batch in predictions['y_true']:
                            for batch_idx in range(batch[0].shape[0]):
                                reformatted_predictions['y_true'].append([output[batch_idx] for output in batch])
                        predictions = reformatted_predictions
                        assert len(predictions['y_true']) == len(predictions['y_pred'])
                else:  # this validation set is a numpy array
                    results = model.evaluate(x=validation_data,
                                             y=validation_targets,
                                             verbose=0,
                                             sample_weight=sample_weights,
                                             batch_size=self.batch_size)
                    if self.record_predictions:  # TODO check if this works
                        predictions = {
                            'y_pred': list(zip(*model.predict(validation_data))),
                            'y_true': list(zip(*validation_targets)),
                        }
                        assert len(predictions['y_true']) == len(predictions['y_pred'])
            else:
                results = [nan for _ in self.model.metrics_names]
                if self.record_predictions:
                    predictions = {
                        'y_pred': [],
                        'y_true': [],
                    }

            if self.record_predictions:
                value_name = self.prefix() + validation_set_name + '_predictions'
                assert predictions is not None
                self.history.setdefault(value_name, []).append(predictions)

            for i, result in enumerate(results):
                value_name = self.prefix() + validation_set_name + '_' + self.model.metrics_names[i]
                self.history.setdefault(value_name, []).append(result)
                if self.verbose == 1:
                    print(self.prefix() + validation_set_name + '_' + self.model.metrics_names[i], result)

    def model_to_evaluate(self) -> Optional[Model]:
        """
        To be overridden by subclasses, i was once using this to implement
        Stochastic Weight Averaging (https://arxiv.org/abs/1803.05407)
        which builds a separate model in callbacks, that is then also evaluated.
        If `None` is returned, no evaluation is done (in that epoch).
        """
        return self.model

    # noinspection PyMethodMayBeStatic
    def prefix(self):
        """
        To be overridden by subclasses, the value returned here will be prepended to the keys in the list of metrics
        """
        return ''

    def results(self):
        """
        I actually don't remember what this method was used for, looks like it returns the results of the last epoch only
        :return: list of pairs (set_name:str, last_results:float)
        """
        if self.history == {}:
            return None
        else:
            results: List[Tuple[str, float]] = [(key, self.history[key][len(self.history[key]) - 1]) for key in
                                                self.history]
            rs: Dict[str, float] = {key: value for (key, value) in results}
            return rs
