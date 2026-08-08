// Copyright (c) 2025 Blankensmithing LLC
// This file is licensed under the GNU Affero General Public License v3.0
// (or later), see https://github.com/torinmb/yolo-touchdesigner/blob/master/LICENSE.txt.

import { INPUT_W, INPUT_H } from "../config.js";
import {
    mapBoxYFlipNorm,
    mapAngleToBottomLeft,
    polygonFromXYWHR,
    normPolyYFlip,
    flipYKeypointsNorm,
} from "./math.js";

export const BINARY_TYPE_SEGMENTATION = 11;
export const BINARY_TYPE_DEPTH = 12;
export const BINARY_DTYPE_FLOAT32 = 2;
export const BINARY_LAYOUT_HW = 2;
export const BINARY_PROTOCOL_VERSION = 1;
export const BINARY_HEADER_BYTES = 16;

export function formatFloatMapBinary(
    type,
    width,
    height,
    data,
    seq,
    frame,
) {
    if (!(data instanceof Float32Array)) {
        throw new TypeError("Binary float-map payload must be a Float32Array");
    }
    if (data.length !== width * height) {
        throw new RangeError(
            `Float-map payload length ${data.length} does not match ${width}x${height}`,
        );
    }
    if (width > 0xffff || height > 0xffff) {
        throw new RangeError("Binary float-map dimensions exceed uint16");
    }

    const buf = new Uint8Array(BINARY_HEADER_BYTES + data.byteLength);
    const dv = new DataView(buf.buffer);
    dv.setUint8(0, type);
    dv.setUint8(1, BINARY_DTYPE_FLOAT32);
    dv.setUint8(2, BINARY_LAYOUT_HW);
    dv.setUint8(3, BINARY_PROTOCOL_VERSION);
    dv.setUint16(4, height, true);
    dv.setUint16(6, width, true);
    dv.setUint32(8, seq >>> 0, true);
    dv.setUint32(12, frame >>> 0, true);

    buf.set(
        new Uint8Array(data.buffer, data.byteOffset, data.byteLength),
        BINARY_HEADER_BYTES,
    );
    return buf.buffer;
}

export function formatPredictions(
    frameId,
    seq,
    keepDet,
    keepPose,
    videoFrame,
    frameSize = null,
) {
    const width = frameSize?.width ?? INPUT_W;
    const height = frameSize?.height ?? INPUT_H;

    const predsDet = keepDet.map((t) => {
        const box = mapBoxYFlipNorm(t.box, width, height);
        // Use Center coordinates (cx, cy) instead of Bottom-Left (tx, ty)
        // to ensure rotation happens around the center of the object in TD.
        const out = {
            tx: box[0] + box[2] * 0.5,
            ty: box[1] + box[3] * 0.5,
            width: box[2],
            height: box[3],
            categoryName: [t.label],
            score: t.score,
            id: t.id,
        };

        if (typeof t.angle === "number" && Number.isFinite(t.angle)) {
            out.angleRadImage = t.angle;
            out.angleRad = mapAngleToBottomLeft(t.angle);
            out.angleDeg = out.angleRad * (180 / Math.PI);
            const polyImg = polygonFromXYWHR(t.box, t.angle);
            out.polygon = normPolyYFlip(polyImg, width, height);
        }
        return out;
    });

    const predsPose = keepPose.map((t) => {
        const box = mapBoxYFlipNorm(t.box, width, height);
        const kpts = flipYKeypointsNorm(t.keypoints, width, height);
        return {
            tx: box[0],
            ty: box[1],
            width: box[2],
            height: box[3],
            categoryName: [t.label],
            score: t.score,
            id: t.id,
            keypoints: kpts,
        };
    });

    return {
        frame: frameId >>> 0,
        seq: seq >>> 0,
        videoFrame,
        width,
        height,
        yolo: predsDet,
        yolo_pose: predsPose,
    };
}
