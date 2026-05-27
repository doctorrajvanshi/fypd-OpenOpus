# Known Issues

*There are currently no known blocking issues in v1.0.0.*

## Resolved Issues
* **MediaPipe Protobuf Parsing Error:** *(Resolved in v1.0.0)* The text-format parsing crash caused by `mediapipe==0.10.13` and `protobuf 5.x` on Python 3.12 has been permanently fixed by migrating the core engine to the modern `mediapipe.tasks.vision.FaceDetector` API.
