# Commands

Use the local virtual environment for all Python commands.

## Install dependencies

```
./run.ps1 -m pip install -r requirements.txt
```

## Install editable package

```
./run.ps1 -m pip install -e .
```

## Run the app

```
./run.ps1 -m copilot_echo.app
```

## List audio input devices

```
./run.ps1 -m copilot_echo.voice.devices
```
