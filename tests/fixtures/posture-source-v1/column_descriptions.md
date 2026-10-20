# Kaggle column descriptions - copy/paste reference

For each group below, open every listed file's "Column descriptions" editor on the Kaggle dataset page and paste in the same column/description text.

## Label files (start_time / end_time / action / is_fall)

**Files:**
- `train/labels/hr_fall_detection_1.csv`
- `train/labels/hr_fall_detection_2.csv`
- `train/labels/hr_fall_detection_3.csv`
- `valid/labels/fall_detection_4.csv`
- `valid/labels/fall_detection_5.csv`
- `valid/labels/fall_detection_6.csv`
- `valid/labels/fall_detection_7.csv`
- `valid/labels/fall_detection_8.csv`
- `valid/labels/fall_detection_9.csv`
- `valid/labels/fall_detection_10.csv`

**Columns:**

- `start_time` (integer): Start of the labelled segment, in seconds from the start of the video.
- `end_time` (integer): End of the labelled segment, in seconds from the start of the video.
- `action` (string): Activity/posture label for this segment (e.g. Stand, Sit, Lie). A hyphenated value (e.g. Stand-Sit) marks a transition between two states. Blank means no activity was assigned yet (e.g. before the subject enters frame).
- `is_fall` (boolean): Whether this segment is labelled as a fall event.

## Static-pose feature files (un-predicted)

**Files:**
- `train/pose-1st-iteration/features_output.csv`
- `train/pose/features_output.csv`
- `train/pose/model1_features_output.csv`
- `train/pose/model2_features_output.csv`

**Columns:**

- `image_name` (string): Source static-pose image file name.
- `is_upright` (boolean): Whether the shoulder line is rotated enough relative to the hip line to indicate an upright torso (part of the standing-vs-lying rule).
- `percent_upright` (numeric): Confidence percentage backing the is_upright classification.
- `stand_left` (string): Left-leg standing classification from hip-knee-ankle bone-length geometry: standing, non_standing, squat, or uncertain_standing/uncertain_squat.
- `stand_right` (string): Right-leg equivalent of stand_left.
- `percent_stand_left` (numeric): Confidence percentage backing the stand_left classification.
- `percent_stand_right` (numeric): Confidence percentage backing the stand_right classification.
- `sit_left` (string): Left-leg sitting classification: sitting, non_sitting, or uncertain_sitting.
- `sit_right` (string): Right-leg equivalent of sit_left.
- `percent_sit_left` (numeric): Confidence percentage backing the sit_left classification.
- `percent_sit_right` (numeric): Confidence percentage backing the sit_right classification.
- `lie_left` (string): Left-side lying classification: lying or non_lying.
- `lie_right` (string): Right-side equivalent of lie_left.

## Static-pose feature files (predicted)

**Files:**
- `train/pose-1st-iteration/features_output_predicted.csv`
- `train/pose/features_output_predicted.csv`
- `train/pose/model1_features_output_predicted.csv`
- `train/pose/model2_features_output_predicted.csv`

**Columns:**

- `image_name` (string): Source static-pose image file name.
- `is_upright` (boolean): Whether the shoulder line is rotated enough relative to the hip line to indicate an upright torso (part of the standing-vs-lying rule).
- `percent_upright` (numeric): Confidence percentage backing the is_upright classification.
- `stand_left` (string): Left-leg standing classification from hip-knee-ankle bone-length geometry: standing, non_standing, squat, or uncertain_standing/uncertain_squat.
- `stand_right` (string): Right-leg equivalent of stand_left.
- `percent_stand_left` (numeric): Confidence percentage backing the stand_left classification.
- `percent_stand_right` (numeric): Confidence percentage backing the stand_right classification.
- `sit_left` (string): Left-leg sitting classification: sitting, non_sitting, or uncertain_sitting.
- `sit_right` (string): Right-leg equivalent of sit_left.
- `percent_sit_left` (numeric): Confidence percentage backing the sit_left classification.
- `percent_sit_right` (numeric): Confidence percentage backing the sit_right classification.
- `lie_left` (string): Left-side lying classification: lying or non_lying.
- `lie_right` (string): Right-side equivalent of lie_left.
- `label` (string): Ground-truth static posture (stand, sit, lie, bend, squat, etc.), parsed from the image filename.
- `predicted_label` (string): The package's rule-based static-posture prediction for this image. Blank where MediaPipe failed to detect any landmarks (this happens on some lying/occluded poses).

## K-means aspect-ratio cluster summary

**Files:**
- `train/pose/grouped_kmeans_static_pose_boundingbox_data.csv`

**Columns:**

- `aspect_ratio` (numeric): Minimum bounding-box aspect ratio within this K-means cluster. NOTE: this file is a pandas multi-index aggregation (groupby(...).agg(['min','max','mean','count'])) exported with duplicate-suffixed column names; row 0 of the data holds the literal sub-column labels ('min','max','mean','count') rather than a value - skip row 0 when loading, or treat it as a second header row.
- `aspect_ratio.1` (numeric): Maximum bounding-box aspect ratio within this K-means cluster (see column 'aspect_ratio' note about row 0).
- `aspect_ratio.2` (numeric): Mean bounding-box aspect ratio within this K-means cluster (see column 'aspect_ratio' note about row 0).
- `aspect_ratio.3` (numeric): Number of images in this K-means cluster (see column 'aspect_ratio' note about row 0).

## Overall bounding-box summary

**Files:**
- `train/pose/grouped_static_pose_boundingbox_data.csv`

**Columns:**

- `aspect_ratio` (numeric): Mean bounding-box aspect ratio across all 113 static pose images. NOTE: same pandas multi-index export artifact as grouped_kmeans_static_pose_boundingbox_data.csv - row 0 of the data holds the literal sub-column label ('mean') rather than a value.
- `relative_width` (numeric): Mean bounding-box width as a fraction of frame width, across all 113 images (see 'aspect_ratio' column note about row 0).
- `relative_height` (numeric): Mean bounding-box height as a fraction of frame height, across all 113 images (see 'aspect_ratio' column note about row 0).

## Bounding-box geometry (focused keypoints)

**Files:**
- `train/pose/static_pose_boundingbox_data.csv`

**Columns:**

- `image_name` (string): Source static-pose image file name.
- `frame_width` (integer): Source image width, in pixels.
- `frame_height` (integer): Source image height, in pixels.
- `aspect_ratio` (numeric): Height/width ratio of the MediaPipe pose bounding box.
- `relative_width` (numeric): Bounding box width as a fraction of the frame width.
- `relative_height` (numeric): Bounding box height as a fraction of the frame height.

## Bounding-box geometry (all 33 keypoints)

**Files:**
- `train/pose/static_pose_boundingbox_data_all_keypoints.csv`

**Columns:**

- `image_name` (string): Source static-pose image file name.
- `frame_width` (integer): Source image width, in pixels.
- `frame_height` (integer): Source image height, in pixels.
- `aspect_ratio` (numeric): Height/width ratio of the MediaPipe pose bounding box.
- `relative_width` (numeric): Bounding box width as a fraction of the frame width.
- `relative_height` (numeric): Bounding box height as a fraction of the frame height.

## Bounding-box geometry (with prediction)

**Files:**
- `train/pose/static_pose_boundingbox_data_bounding_box_size_predicted.csv`

**Columns:**

- `image_name` (string): Source static-pose image file name.
- `frame_width` (integer): Source image width, in pixels.
- `frame_height` (integer): Source image height, in pixels.
- `aspect_ratio` (numeric): Height/width ratio of the MediaPipe pose bounding box.
- `relative_width` (numeric): Bounding box width as a fraction of the frame width.
- `relative_height` (numeric): Bounding box height as a fraction of the frame height.
- `label` (string): Ground-truth static posture, parsed from the image filename.
- `predicted_label` (string): Posture prediction from a bounding-box-aspect-ratio-only classifier - an alternative to the landmark-angle-based classifier, useful when MediaPipe landmark detection itself fails (e.g. on occluded or lying poses).

## Per-frame video results

**Files:**
- `train/results of static pose classifier on training videos/hr_fall_detection_static_pose_class_on_video_1_results.csv`
- `train/results of static pose classifier on training videos/hr_fall_detection_static_pose_class_on_video_2_results.csv`
- `train/results of static pose classifier on training videos/hr_fall_detection_static_pose_class_on_video_3_results.csv`

**Columns:**

- `file_name` (integer): Frame index within the source video.
- `max_value` (numeric): Peak frame-differencing magnitude used to flag motion at this frame.
- `process_image` (boolean): Whether this frame was selected for pose estimation. Frames are motion-triggered rather than exhaustively sampled, so not every frame is processed.
- `label` (string): Ground-truth posture for this frame, derived from the manual activity-label CSV for the matching video and timestamp.
- `prediction` (string): The package's rule-based static-posture prediction for this frame. Blank where the frame was not processed or no pose was detected.
- `image_name` (string): Unused in this per-frame file (carried over from the shared feature-extraction function); always blank.
- `is_upright` (boolean): Whether the shoulder line is rotated enough relative to the hip line to indicate an upright torso (part of the standing-vs-lying rule).
- `percent_upright` (numeric): Confidence percentage backing the is_upright classification.
- `stand_left` (string): Left-leg standing classification from hip-knee-ankle bone-length geometry: standing, non_standing, squat, or uncertain_standing/uncertain_squat.
- `stand_right` (string): Right-leg equivalent of stand_left.
- `percent_stand_left` (numeric): Confidence percentage backing the stand_left classification.
- `percent_stand_right` (numeric): Confidence percentage backing the stand_right classification.
- `sit_left` (string): Left-leg sitting classification: sitting, non_sitting, or uncertain_sitting.
- `sit_right` (string): Right-leg equivalent of sit_left.
- `percent_sit_left` (numeric): Confidence percentage backing the sit_left classification.
- `percent_sit_right` (numeric): Confidence percentage backing the sit_right classification.
- `lie_left` (string): Left-side lying classification: lying or non_lying.
- `lie_right` (string): Right-side equivalent of lie_left.
