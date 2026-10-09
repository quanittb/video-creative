"""Regenerate the stock office torso matte from the portrait and calibrated mask."""

from pathlib import Path

import cv2
import numpy as np


ROOT_DIR = Path(__file__).resolve().parents[1]
MASK_PATH = ROOT_DIR / "assets" / "driving_templates" / "office_torso_silhouette_mask.png"
SOURCE_PATH = ROOT_DIR / "assets" / "characters" / "nhanvatnam" / "asian_male_office_1080p.png"
INTERIOR_MASK_PATH = ROOT_DIR / "assets" / "driving_templates" / "office_torso_motion_mask.png"

# Trace the shirt and shoulder outline in source-image coordinates. The inward
# neckline path leaves exposed neck skin out of the moving foreground.
SHIRT_OUTLINE = np.array([
    [399, 958], [372, 966], [345, 976], [317, 989], [290, 1001],
    [263, 1010], [238, 1020], [216, 1032], [200, 1048], [188, 1069],
    [178, 1099], [169, 1141], [164, 1190], [153, 1242], [140, 1279],
    [903, 1279], [890, 1237], [886, 1193], [880, 1153], [873, 1118],
    [861, 1085], [845, 1057], [825, 1038], [803, 1024], [777, 1014],
    [745, 1003], [713, 991], [683, 979], [650, 967], [625, 958],
    [606, 965], [597, 980], [591, 1001], [580, 1019], [563, 1035],
    [545, 1046], [529, 1051], [512, 1032], [495, 1047], [478, 1045],
    [461, 1036], [445, 1021], [434, 1002], [426, 981], [417, 966],
], dtype=np.int32)
NECK_EXCLUSION = np.array([
    [420, 950], [604, 950], [598, 978], [590, 1000], [578, 1020],
    [560, 1036], [539, 1045], [522, 1035], [510, 1028], [494, 1044],
    [476, 1042], [458, 1033], [443, 1018], [432, 1000], [426, 978],
], dtype=np.int32)


def main() -> None:
    source = cv2.imread(str(SOURCE_PATH), cv2.IMREAD_COLOR)
    interior = cv2.imread(str(INTERIOR_MASK_PATH), cv2.IMREAD_GRAYSCALE)
    if source is None or interior is None or source.shape[:2] != interior.shape:
        raise RuntimeError("Stock office source or calibrated interior mask is missing or mismatched.")
    height, width = interior.shape
    candidate = np.zeros((height, width), dtype=np.uint8)
    neck = np.zeros_like(candidate)
    cv2.fillPoly(candidate, [SHIRT_OUTLINE], 255)
    cv2.fillPoly(neck, [NECK_EXCLUSION], 255)

    candidate_binary = (candidate > 0).astype(np.uint8)
    inner_distance = cv2.distanceTransform(candidate_binary, cv2.DIST_L2, 5)
    labels = np.full((height, width), cv2.GC_BGD, dtype=np.uint8)
    labels[candidate_binary > 0] = cv2.GC_PR_FGD
    labels[(candidate_binary > 0) & (inner_distance <= 10.0)] = cv2.GC_PR_BGD

    foreground_seeds = (interior > 128) & (neck == 0) & (candidate_binary > 0)
    foreground_seeds = cv2.erode(
        foreground_seeds.astype(np.uint8), np.ones((3, 3), dtype=np.uint8), iterations=2
    ) > 0
    labels[foreground_seeds] = cv2.GC_FGD
    background_model = np.zeros((1, 65), dtype=np.float64)
    foreground_model = np.zeros((1, 65), dtype=np.float64)
    cv2.grabCut(
        source, labels, None, background_model, foreground_model, 8, cv2.GC_INIT_WITH_MASK
    )
    mask = np.isin(labels, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
    mask &= candidate_binary
    mask[neck > 0] = 0
    MASK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(MASK_PATH), mask * 255):
        raise RuntimeError(f"Could not write calibrated mask: {MASK_PATH}")
    print(MASK_PATH)


if __name__ == "__main__":
    main()
