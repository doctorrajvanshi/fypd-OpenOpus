# Known Issues

1. **MediaPipe Protobuf Parsing Error on Python 3.12**
   - **Issue:** When running the application, you may encounter an error similar to: `[libprotobuf ERROR ...] Error parsing text-format mediapipe.CalculatorGraphConfig: 15:22: Expected identifier, got: \`. This is caused by an incompatibility between `mediapipe==0.10.13` and newer versions of the `protobuf` package (version 5.x) in Python 3.12 environments.
   - **Solution:** The application requires specific older versions of both packages to parse the text definitions correctly. Run the following command in your terminal to force the environment to install the compatible versions:
     ```bash
     pip install mediapipe==0.10.13 protobuf==4.25.3 --force-reinstall
     ```
