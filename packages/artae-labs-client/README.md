# Artae Labs client

This package is the narrow integration boundary between the camera intelligence
platform and the internal Artae Labs API. It supports creating an index, uploading
a video through the presigned-object-storage flow, polling indexing status, and
searching timestamped moments.

`ARTAE_LABS_INDEX_ID` optionally selects the existing shared index used by the
platform's background evidence worker. The manual smoke CLI can still create its
own index independently.

It intentionally does not depend on the webcam or YOLO code. A slow or unavailable
intelligence service must not stop the real-time detection loop.

See the repository root `README.md` for installation and smoke-test commands.

The client uses one authenticated HTTP session for Labs and a separate
unauthenticated session for presigned object-storage PUT requests. That separation
prevents the Labs API key from leaking to the storage host.
