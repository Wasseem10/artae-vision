# Empty-chair regression fixtures

These two people-free scenes check that the browser pose worker does not
return a person for visible chairs. Both images are CC0 and were retrieved
from Wikimedia Commons on September 29, 2026:

- `empty-chairs.jpg`: [Empty Chairs.jpg](https://commons.wikimedia.org/wiki/File:Empty_Chairs.jpg) by Kullatan Kin; Wikimedia 960-pixel thumbnail.
- `empty-classroom.jpg`: [Empty class room.jpg](https://commons.wikimedia.org/wiki/File:Empty_class_room.jpg) by Saral Shots; Wikimedia 1280-pixel thumbnail.

With the app running locally, set `ARTAE_BENCHMARK_URL` if needed and run
`node scripts/check-chair-negative.cjs`. The script runs 31 frames per image
through the same four-pose worker used by the live monitor. It fails if even
one frame returns a raw pose. These still images cover two chair scenes,
not every camera angle, lighting condition, or moving background.
