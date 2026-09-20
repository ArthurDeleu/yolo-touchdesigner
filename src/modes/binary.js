// Copyright (c) 2025 Blankensmithing LLC
// This file is licensed under the GNU Affero General Public License v3.0
// (or later), see https://github.com/torinmb/yolo-touchdesigner/blob/master/LICENSE.txt.

import { INPUT_W, INPUT_H } from "../config.js";
import {
    depthSession,
    detSession,
    poseSession,
    segSession,
} from "../inference/onnx.js";
import { toInputTensorFromU8CHW } from "../inference/io.js";
import { runInferencePipeline } from "../pipeline.js";
import { setStatus } from "../ui.js";
import { reportClientError, setReportSender } from "../utils/report.js";
export { reportClientError };

let latestJob = null;
let isProcessing = false;

function parseHeader(buf) {
    if (buf.byteLength < 16) return null;
    const dv = new DataView(buf);
    const type = dv.getUint8(0);
    const dtype = dv.getUint8(1);
    const layout = dv.getUint8(2);
    const H = dv.getUint16(4, true);
    const W = dv.getUint16(6, true);
    const seq = dv.getUint32(8, true);
    const td = dv.getUint32(12, true);
    if (type !== 10 || dtype !== 1 || layout !== 1) return null; // require u8 CHW
    // payload is a view
    const payload = new Uint8Array(buf, 16);
    return { H, W, seq, td, payload };
}

let _framesAccepted = 0;
export function handleBinaryMessage(data) {
    if (data.byteLength < 16) return;

    // Only support Legacy Header U8 CHW
    const job = parseHeader(data);
    if (job && job.H === INPUT_H && job.W === INPUT_W) {
        if (_framesAccepted++ === 0) {
            // one-time beacon so the TD side can tell "frames arrive" from "nothing arrives"
            reportClientError("info:first-frame-accepted", `H=${job.H} W=${job.W} seq=${job.seq} bytes=${data.byteLength}`);
        }
        latestJob = job;
        pumpBinary();
    } else {
        const dv = new DataView(data);
        reportClientError(
            "frame-rejected",
            `type=${dv.getUint8(0)} dtype=${dv.getUint8(1)} layout=${dv.getUint8(2)} H=${dv.getUint16(4, true)} W=${dv.getUint16(6, true)} bytes=${data.byteLength} (need type=10 dtype=1 layout=1 ${INPUT_H}x${INPUT_W})`,
        );
    }
}

export function setWebSocketSender(senderFn) {
    _sender = senderFn;
    setReportSender(senderFn);
}

let _sender = null;

async function pumpBinary() {
    if (isProcessing) return;
    isProcessing = true;

    try {
        const job = latestJob;
        latestJob = null;

        if (!job) return;
        if (!detSession && !poseSession && !segSession && !depthSession) {
            reportClientError("no-sessions", "frame received but no model session is loaded (model URL / WebGPU?)");
            return;
        }

        const input = toInputTensorFromU8CHW(job.payload, INPUT_H, INPUT_W);

        await runInferencePipeline(
            input,
            job.td,
            job.seq,
            0 /* videoFrame */,
            _sender,
        );
    } catch (e) {
        console.error(e);
        setStatus(`Error (binary): ${e?.message || e}`);
        reportClientError("binary-pipeline", e);
    } finally {
        isProcessing = false;
        if (latestJob) queueMicrotask(pumpBinary);
    }
}
