// Ship diagnostics from the page to TouchDesigner over the existing socket.
//
// TD's onWebSocketReceiveText routes by substring: anything containing "type"
// goes to the predictions DAT (overwritten ~30x/s by predictions, useless for
// a one-off report), "webcamDevices" -> webcam_list, "tick" -> tick, and
// "lastFrameTime" -> the status DAT, which nothing else writes in TOP-input
// mode. So reports carry a lastFrameTime key and are scrubbed of the other
// routing substrings. Read them in TD from yolo_server/status.
let _sender = null;
let _lastKey = "";

export function setReportSender(fn) {
    _sender = fn;
}

function scrub(s) {
    return String(s)
        .replace(/type/g, "typ_e")
        .replace(/tick/g, "tic_k")
        .replace(/webcamDevices/g, "webcam_Devices");
}

// One entry per distinct (where, message), never per frame. Every send carries
// the full history (last 12), so the status DAT always shows the whole story
// in order rather than only the most recent report.
const _history = [];
export function reportClientError(where, e) {
    if (!_sender) return;
    const message = String(e?.message || e);
    const key = where + message;
    if (key === _lastKey) return;
    _lastKey = key;
    _history.push({
        at: new Date().toISOString().slice(11, 23),
        where: scrub(where),
        message: scrub(message).slice(0, 400),
        stack: scrub(String(e?.stack || "")).slice(0, 600),
    });
    if (_history.length > 12) _history.shift();
    _sender({ lastFrameTime: -1, report: true, href: scrub(location.href), reports: _history });
}
