# Known Issues

*There are currently no known blocking issues in v1.2.1.*

## Resolved Issues

* **Silent render failures when ImageMagick is missing:** *(Resolved in v1.2.1)*
  ImageMagick detection only ever probed two hardcoded paths and accepted them on
  existence alone, and a failed job left its clip cards spinning on "processing"
  forever, so the real cause appeared only in the log file. Detection now searches
  the app data folder, the app folder, `PATH` and versioned Program Files installs,
  and executes each candidate before accepting it. Failures surface as a
  *Setup Required* banner in the dashboard and on the new `/health` endpoint.

* **Visual style, B-roll and background music were ignored:** *(Resolved in v1.2.1)*
  The `Clip` request model did not declare `style`, `bgm_mood` or `broll_keywords`,
  so Pydantic dropped all three before the payload reached the rendering engine.
  Every clip rendered in the `hormozi` style with no B-roll and no music
  regardless of what was selected.

* **Completed clips 404 in the dashboard:** *(Resolved in v1.2.1)* The frontend
  rebuilt video URLs from the raw clip title while the backend wrote sanitized
  filenames, so any title containing `: ? " < > | / \` or `#` produced an
  unreachable URL. The backend now reports the real filename.

* **Face tracking accuracy:** *(Resolved in v1.2.1)* Frames were passed through
  `cv2.cvtColor(..., COLOR_BGR2RGB)` even though MoviePy already supplies RGB,
  so MediaPipe scored colour-inverted images.

* **Duplicated or dropped footage at segment boundaries:** *(Resolved in v1.2.1)*
  Smart transition snapping moved a segment's end without moving the next
  segment's start.

* **MediaPipe Protobuf Parsing Error:** *(Resolved in v1.0.0)* The text-format parsing crash caused by `mediapipe==0.10.13` and `protobuf 5.x` on Python 3.12 has been permanently fixed by migrating the core engine to the modern `mediapipe.tasks.vision.FaceDetector` API.
