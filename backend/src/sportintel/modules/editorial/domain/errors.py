from sportintel.platform.errors import Conflict, Forbidden


class EventStatusInvalid(Conflict):
    code = "draft.event_status_invalid"
    title = "Event status does not allow drafts"


class GenerationInProgress(Conflict):
    code = "draft.generation_in_progress"
    title = "Draft generation in progress"


class DisclaimerRemovalForbidden(Forbidden):
    code = "draft.disclaimer_removal_forbidden"
    title = "Only editors can remove the disclaimer"
