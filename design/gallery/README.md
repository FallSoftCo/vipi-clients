# Publish Vipi design reviews

Publish each original concept, substantial revision, native capture and interaction recording when it is ready to look at. Keep a revision under its own stable link so reviewers can compare it with the next one. Describe whether the material is editable artwork, a color study made from a screenshot, or a capture from a running app. Use controlled test conversations. Keep licensed Mobbin screens in the private reference collection.

The [Vipi review shelf](https://system76-pc.tailb77f2a.ts.net/8bar/vipi-studio-20261120/) and its individual cards on the [main gallery](https://system76-pc.tailb77f2a.ts.net/8bar/) use the existing system76 publisher. Prepare a UTF-8 JSON file with a new descriptive slug, a title, a short description, and an ordered list of items. Each item has a human-readable `label` and an absolute `path` to a reviewed local asset. Put a PNG, JPEG or WebP poster first. SVG, PDF and MP4 originals can follow. Give each file a distinct name within the batch.

Run this from the Vipi working tree on system76.

```sh
python3 design/gallery/publish_review.py /absolute/path/to/batch.json
```

The publisher registers the batch, adds a main-gallery card, checks that the live catalog lists the card, and compares each served download with its source. It prints the gallery URL after verification. Use the same slug to add downloads to a previous batch. Give changed artwork a new slug. Send the link to the project owner with the fact they should inspect.

The shared publisher state and asset manifests live under `/mnt/extradrive1/vipi-builds/gallery-publication-r01`. After changing the gallery layout, use the shared `showcase/check.mjs` and the Vipi-specific phone-width and desktop check on the native Mac under `~/Development/vipi-gallery-qa-20261120`.
