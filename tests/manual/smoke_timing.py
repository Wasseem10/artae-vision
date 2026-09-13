"""Opt-in paid AWS smoke test using synthetic, non-personal color-card frames.

Run: .venv/Scripts/python tests/manual/smoke_timing.py
This validates the image/state/refinement contract, NOT fall/parking accuracy.
"""
import base64
import io

import httpx
from PIL import Image, ImageDraw


def frame(at):
    image = Image.new("RGB", (320, 240), "white")
    if 3 <= at < 11:
        ImageDraw.Draw(image).rectangle((60, 60, 260, 180), fill="red")
    output = io.BytesIO()
    image.save(output, format="JPEG")
    return {"at_seconds": at, "jpeg": base64.b64encode(output.getvalue()).decode()}


def main():
    with httpx.Client(base_url="https://artae-vision-api.vercel.app/api/v1", timeout=70) as client:
        response = client.post("/browser-sessions/public-demo", json={
            "prompt": "A large red rectangle is visible on a white background.", "detailed": True,
        })
        response.raise_for_status()
        token = response.json()["token"]
        cases = [
            ([0, 2, 4, 6, 8, 10, 12, 14], False),
            ([2 + 2 * i / 7 for i in range(8)], True),
            ([10 + 2 * i / 7 for i in range(8)], True),
        ]
        for times, refinement in cases:
            response = client.post("/browser-sessions/public-demo/analyze", json={
                "token": token, "frames": [frame(at) for at in times], "refinement": refinement,
            })
            response.raise_for_status()
            result = response.json()
            states = result["conditions"][0]["frame_states"]
            expected = ["active" if 3 <= at < 11 else "inactive" for at in times]
            print({"refinement": refinement, "times": [round(at, 3) for at in times], "states": states}, flush=True)
            assert states == expected, "Model observations differ from this synthetic fixture"
            if refinement:
                assert result["event"] is None, "Refinement should not send duplicate alerts"
        print("PASS: real AWS base scan and both boundary rechecks matched the controlled fixture.")


if __name__ == "__main__":
    main()
