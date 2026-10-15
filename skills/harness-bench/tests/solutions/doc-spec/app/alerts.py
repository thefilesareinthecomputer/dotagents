"""Zone flow alerts, per docs/alerts.md."""


def evaluate(readings, thresholds):
    state, faulting, events = {}, set(), []
    for t, zone, flow in readings:
        if flow < 0:
            if zone not in faulting:
                faulting.add(zone)
                events.append({"t": t, "zone": zone, "state": "fault"})
            continue
        faulting.discard(zone)
        limits = thresholds.get(zone, thresholds["default"])
        current = state.get(zone, "normal")
        if current == "normal" and flow >= limits["high"]:
            state[zone] = "alert"
            events.append({"t": t, "zone": zone, "state": "alert"})
        elif current == "alert" and flow <= limits["low"]:
            state[zone] = "normal"
            events.append({"t": t, "zone": zone, "state": "normal"})
    return events
