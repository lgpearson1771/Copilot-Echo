# Train a Custom Wake Word: "Hey Echo"

This guide walks you through training a custom openwakeword model for the phrase "hey echo" using Google Colab.

## Run the notebook in Colab
Open the automatic training notebook here:
https://colab.research.google.com/github/dscripka/openWakeWord/blob/main/notebooks/automatic_model_training.ipynb

## Steps
1) Open the Colab notebook and make a copy to your Drive.
2) Find the cell where you define the wake phrase.
3) Set the phrase to:
   - "hey echo"
4) Run the notebook cells in order.
5) When the notebook finishes, download the exported model file (.tflite or .onnx).

## Add the model to Copilot Echo
1) Save the model under `models/` in this repo, for example:
   - `models/hey_echo.tflite`
2) Update your config:

```
voice:
  wakeword_engine: "openwakeword"
  wakeword_models: ["models/hey_echo.tflite"]
```

## Tips
- If you get false activations, increase `wakeword_threshold` slightly (e.g., 0.6 -> 0.7).
- If it misses activations, lower the threshold (e.g., 0.6 -> 0.5).
