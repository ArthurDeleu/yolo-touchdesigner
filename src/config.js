// Copyright (c) 2025 Blankensmithing LLC
// This file is licensed under the GNU Affero General Public License v3.0
// (or later), see https://github.com/torinmb/yolo-touchdesigner/blob/master/LICENSE.txt.

import { normalizeRotationDeg } from "./utils/orientation.js";

export const qs = new URLSearchParams(location.search);

const boolish = (v, def = false) => {
    if (v == null) return def;
    const s = String(v);
    if (/^(true|on|yes)$/i.test(s)) return true;
    const n = parseFloat(s);
    if (!Number.isNaN(n)) return n !== 0;
    return false;
};

const pick = (...names) => {
    for (const n of names) if (n && qs.has(n)) return qs.get(n);
    return null;
};

export const getStr = (names, fallback) => {
    const v = pick(...names);
    return v != null ? v : fallback;
};

export const getBool = (names, fallback) => {
    const v = pick(...names);
    return v != null ? boolish(v, fallback) : fallback;
};

export const getNum = (primaryNames, fallback, commonFallbackName) => {
    for (const n of primaryNames) {
        if (qs.has(n)) {
            const x = parseFloat(qs.get(n));
            if (!Number.isNaN(x)) return x;
        }
    }
    if (commonFallbackName && qs.has(commonFallbackName)) {
        const x = parseFloat(qs.get(commonFallbackName));
        if (!Number.isNaN(x)) return x;
    }
    return fallback;
};

export const getInt = (primaryNames, fallback, commonFallbackName) => {
    for (const n of primaryNames) {
        if (qs.has(n)) {
            const x = parseInt(qs.get(n), 10);
            if (!Number.isNaN(x)) return x;
        }
    }
    if (commonFallbackName && qs.has(commonFallbackName)) {
        const x = parseInt(qs.get(commonFallbackName), 10);
        if (!Number.isNaN(x)) return x;
    }
    return fallback;
};

/* ================================
   Global config / toggles
================================ */
export const WS_PORT = qs.get("wsPort") || "62309";
export const USE_BINARY = getBool(["binary"], false);
export const USE_CPU = getBool(["cpu", "CPU"], false);
export const DEV_MODE = getBool(
    ["dev", "Dev", "debug", "Debug", "DEBUG"],
    false,
);

// Stream toggles + models
export let ENABLE_DET = getBool(
    ["Objecttrackingenabled", "ObjectTrackingEnabled"],
    true,
);
export let ENABLE_POSE = getBool(
    ["Posetrackingenabled", "pose", "PoseTrackingEnabled"],
    true,
);
export let ENABLE_SEG = getBool(
    ["Segmentationenabled", "segmentation", "SegmentationEnabled"],
    false,
);
export let ENABLE_DEPTH = getBool(
    ["Depthenabled", "depth", "DepthEnabled"],
    false,
);
export let PERSON_SEG_ONLY = getBool(
    ["Personsegonly", "PoseSegOnly", "personSegOnly"],
    false,
);

export let MODEL_DETECT_KEY = getStr(
    ["Objecttrackingmodel", "Obecttrackingmodel", "ObjectTrackingModel"],
    "yolo11n",
);
export let MODEL_POSE_KEY = getStr(["Posemodel", "PoseModel"], "yolo11n-pose");
export let MODEL_SEG_KEY = getStr(
    ["Segmentationmodel", "SegmentationModel"],
    "yolo26n-seg",
);
export let MODEL_DEPTH_KEY = getStr(
    ["Depthmodel", "DepthModel"],
    "yolo26n-depth",
);

// Legacy single `model=` inference logic
const legacyModel = qs.get("model");
const anyToggleProvided = [
    "Poseenabled",
    "pose",
    "Objecttrackingenabled",
    "ObjectTrackingEnabled",
    "detect",
    "Segmentationenabled",
    "segmentation",
    "SegmentationEnabled",
    "Depthenabled",
    "depth",
    "DepthEnabled",
].some((k) => qs.has(k));

if (legacyModel && !anyToggleProvided) {
    if (/pose/i.test(legacyModel)) {
        ENABLE_POSE = true;
        ENABLE_DET = false;
        MODEL_POSE_KEY = legacyModel;
    } else {
        ENABLE_DET = true;
        ENABLE_POSE = false;
        MODEL_DETECT_KEY = legacyModel;
    }
}

// Per-task thresholds
export const DET_SCORE_T = getNum(["Detscoret"], 0.4, "Scoret");
export const DET_IOU_T = getNum(["Detiout"], 0.45, "Iout");
export const DET_TOPK = getInt(["Dettopk"], 100, "Topk");

export const SEG_SCORE_T = getNum(["Segscoret"], 0.2, "Scoret");
export const SEG_TOPK = getInt(["Segtopk"], 100, "Topk");
export const SEG_DECAY_LIMIT = getInt(["Segdecaylimit", "segDecayLimit"], 3);

// What the integer part of the packed segmentation map encodes:
//   "instance" -> a tracked instance id (each body keeps its own id/colour across frames)
//   "class"    -> the COCO class id (legacy: all persons share one id)
export const SEG_PACK_MODE = getStr(["Segpackmode", "segPackMode"], "instance");
// Instance ids are packed into the integer part of a float32 whose fraction
// holds the mask alpha. Float32 has a 23-bit mantissa, so the alpha resolution
// is ulp(id): at id 4096 that is 2^-11 (fine), at id 1e6 it is 2^-3 (unusable).
// Track ids grow monotonically for the life of the page, so wrap them.
// Packed instance ids live in [SEG_ID_BASE, SEG_ID_WRAP): starting at 100 keeps
// them disjoint from the 80 COCO class ids, so a value in the map is
// unambiguous about which mode produced it (class ids never exceed 79).
export const SEG_ID_WRAP = getInt(["Segidwrap", "segIdWrap"], 4096);
export const SEG_ID_BASE = 100;

export const POSE_SCORE_T = getNum(["Posescoret"], 0.35, "Scoret");
export const POSE_IOU_T = getNum(["Poseiout"], 0.45, "Iout");
export const POSE_TOPK = getInt(["Posetopk"], 50, "Topk");

// Tracker settings
export const DET_TRK_IOU = getNum(["Detrkiou"], 0.5, "Trkiou");
export const DET_TRK_TTL = getInt(["Detrkttl"], 2, "Trkttl");
export const POSE_TRK_IOU = getNum(["Posetrkiou"], 0.5, "Trkiou");
export const POSE_TRK_TTL = getInt(["Posetrkttl"], 2, "Trkttl");
// Segmentation instance tracker (only used when SEG_PACK_MODE === "instance").
// A slightly longer TTL than det/pose: a re-id after a brief occlusion is a
// visible colour flip on the wall, a stale box for 4 frames is not.
export const SEG_TRK_IOU = getNum(["Segtrkiou"], 0.5, "Trkiou");
export const SEG_TRK_TTL = getInt(["Segtrkttl"], 4, "Trkttl");

// Webcam options
export const WEBCAM_LABEL = getStr(["webcamLabel"], null);
export const FLIP_HORIZONTAL = USE_BINARY
    ? false
    : getBool(["flipHorizontal"], true);
export const FLIP_VERTICAL = USE_BINARY
    ? false
    : getBool(["flipVertical"], false);
export const WEBCAM_ROTATION_DEG = USE_BINARY
    ? 0
    : normalizeRotationDeg(getInt(["webcamRotation", "rotate", "rotation"], 0));

// Constants
export const INPUT_W = 640;
export const INPUT_H = 640;
export const WEBCAM_INPUT_W = getInt(["webcamInputW", "inputW"], INPUT_W);
export const WEBCAM_INPUT_H = getInt(["webcamInputH", "inputH"], INPUT_H);
