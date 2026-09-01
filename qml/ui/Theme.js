// Small helpers over app.theme (a plain map from harness/config.py). Pure functions only.
.pragma library

function phaseColor(theme, phase) {
    switch (phase) {
    case "planning": return theme.phasePlanning
    case "implementing": return theme.phaseImplementing
    case "done": return theme.phaseDone
    case "canceled": return theme.phaseCanceled
    default: return theme.phaseTodo            // backlog, todo
    }
}

function phaseTitle(phase) {
    return phase ? phase.charAt(0).toUpperCase() + phase.slice(1) : ""
}

// Context/agent status → dot color
function statusColor(theme, status) {
    switch (status) {
    case "working": case "starting": return theme.live
    case "idle": return theme.settled
    case "failed": return theme.danger
    default: return theme.textDim              // stopped, none
    }
}

function hex(color) {  // "#rrggbb" for image://icon URLs (drops the alpha byte QML colors may carry)
    var s = String(color)
    return s.length === 9 ? s.slice(3) : s.slice(1)
}
