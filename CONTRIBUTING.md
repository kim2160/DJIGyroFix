# Contributing

Thanks for helping improve DJI Gyro Fix.

## Development setup

The runtime uses only the Python 3.12 standard library. Run the desktop app with:

```powershell
python app.py
```

Run the regression suite before submitting a change:

```powershell
python -m compileall -q app.py gyrofix tests tools
python -m unittest discover -s tests -v
```

Build the Windows executable with:

```powershell
.\build_exe.bat
```

## Pull requests

- Keep original videos and generated outputs out of commits.
- Add a regression test for parser, smoothing, or output-writing fixes.
- Do not change bytes outside selected DJI quaternion fields.
- Describe the DJI camera/model and metadata variant used for manual testing.
- Avoid committing proprietary or personally identifying video samples.
