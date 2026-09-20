// Copyright (c) 2025 Blankensmithing LLC
// This file is licensed under the GNU Affero General Public License v3.0
// (or later), see https://github.com/torinmb/yolo-touchdesigner/blob/master/LICENSE.txt.

import {
    runDetect,
    runPose,
    runSeg,
    runDepth,
    detSession,
    poseSession,
    segSession,
    depthSession,
    device,
} from "./inference/onnx.js";
import { trackerDet, trackerPose } from "./state.js";
import {
    BINARY_TYPE_DEPTH,
    BINARY_TYPE_SEGMENTATION,
    formatFloatMapBinary,
    formatPredictions,
} from "./utils/protocol.js";
import { setStatus } from "./ui.js";
import { reportClientError } from "./utils/report.js";
let _segNullFrames = 0;

export async function runInferencePipeline(
    inputTensor,
    frameId,
    seq,
    videoFrame,
    sender,
) {
    // 1. Run Inference
    // usage of sessions is guarded by checks in runDetect/runPose,
    // but we check existence here to determine "active" streams for tracking/sending

    let keepDet = [];
    let keepPose = [];
    let segResult = null;
    let depthResult = null;

    if (detSession) keepDet = await runDetect(inputTensor);
    if (poseSession) keepPose = await runPose(inputTensor);
    if (segSession) {
        segResult = await runSeg(inputTensor);
        if (!segResult && ++_segNullFrames === 5)
            reportClientError("seg-null:runSeg", "5 frames with seg session but no seg result (see seg-null:* report before this one)");
    }
    if (depthSession) depthResult = await runDepth(inputTensor);

    // Track frame stats
    window._frameCount = (window._frameCount || 0) + 1;
    if (window._frameCount % 30 === 0) {
        const detC = keepDet ? keepDet.length : 0;
        const poseC = keepPose ? keepPose.length : 0;
        const backend = device ? "WebGPU" : "CPU";
        setStatus(
            `Pipeline: det=${detC} pose=${poseC} seg=${segResult ? 1 : 0} depth=${depthResult ? 1 : 0} | frame=${window._frameCount} | ${backend}`,
        );
    }

    // 2. Update Trackers
    // Only update trackers if the corresponding model is active.
    // Use empty array if active but no detections found.
    const tracksDet = detSession ? trackerDet.update(keepDet) : [];
    const tracksPose = poseSession ? trackerPose.update(keepPose) : [];

    // 3. Format Output
    const msg = formatPredictions(
        frameId,
        seq,
        tracksDet,
        tracksPose,
        videoFrame,
    );

    // 4. Send Message via Callback
    if (sender) {
        // Segmentation Binary
        if (segResult) {
            const { width, height, data } = segResult;
            sender(
                formatFloatMapBinary(
                    BINARY_TYPE_SEGMENTATION,
                    width,
                    height,
                    data,
                    seq,
                    frameId,
                ),
            );
        }

        // Raw metric Depth Binary (FP32 meters; no normalization/inversion)
        if (depthResult) {
            const { width, height, data } = depthResult;
            sender(
                formatFloatMapBinary(
                    BINARY_TYPE_DEPTH,
                    width,
                    height,
                    data,
                    seq,
                    frameId,
                ),
            );
        }

        // Standard JSON
        if (detSession && poseSession) {
            sender({ ...msg, type: "yolo_combined" });
        } else if (detSession) {
            // Trim unused fields for bandwidth
            delete msg.yolo_pose;
            sender({ ...msg, type: "yolo", predictions: msg.yolo });
        } else if (poseSession) {
            delete msg.yolo;
            sender({ ...msg, type: "yolo_pose", predictions: msg.yolo_pose });
        } else if (segSession || depthSession) {
            // Dense-output-only mode: keep flow control and JSON protocol alive.
            delete msg.yolo_pose;
            sender({ ...msg, type: "yolo", predictions: [] });
        }
    }
}
