from sportintel.platform.errors import Conflict, Forbidden, NotFound, ValidationFailed


class InvalidTransition(Conflict):
    code = "event.invalid_transition"
    title = "Transition not allowed"


class TransitionForbidden(Forbidden):
    code = "event.transition_forbidden"
    title = "Transition not allowed for this role"


class ReasonRequired(ValidationFailed):
    code = "event.reason_required"
    title = "Rejection reason is required"


class CommentRequired(ValidationFailed):
    code = "event.comment_required"
    title = "Comment is required"


class OverrideReasonRequired(ValidationFailed):
    code = "event.override_reason_required"
    title = "Override reason is required"


class ArticleNotInEvent(NotFound):
    code = "event.article_not_in_event"
    title = "Article does not belong to the event"


class MergeNotAllowed(Conflict):
    code = "event.merge_not_allowed"
    title = "Merge not allowed"


class SameEvent(ValidationFailed):
    code = "event.same_event"
    title = "Source and target are the same event"
