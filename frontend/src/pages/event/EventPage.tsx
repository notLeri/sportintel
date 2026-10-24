import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/entities/user";
import { EventDetails } from "@/features/event-details";
import { BriefPanel } from "@/features/event-brief";
import {
  EditButton,
  EditEventForm,
  MergeButton,
  MoveArticleMenu,
  OverrideAssessmentPopover,
  UpdatesSinceEditBanner,
} from "@/features/event-edit";
import { HistoryTab } from "@/features/event-history";
import { WorkflowActions } from "@/features/event-workflow";
import { DraftPanel } from "@/features/telegram-draft";

const route = getRouteApi("/events/$eventId");

export function EventPage() {
  const { eventId } = route.useParams();
  const me = useMe();
  // Режим правки привязан к событию: смена события его закрывает.
  const [editingId, setEditingId] = useState<string | undefined>();
  const editing = editingId !== undefined && editingId === eventId;
  const setEditing = (on: boolean) => setEditingId(on ? eventId : undefined);
  const navigate = useNavigate();
  return (
    <div className="mx-auto max-w-3xl">
      <EventDetails
        key={eventId}
        eventId={eventId}
        timeZone={me.timezone}
        slots={{
          actions: (e) => (
            <>
              <EditButton onClick={() => setEditing(true)} />
              <MergeButton event={e} />
              <WorkflowActions event={e} />
            </>
          ),
          articleAction: (e, a) => <MoveArticleMenu event={e} article={a} />,
          relevanceAction: (e) => <OverrideAssessmentPopover event={e} kind="relevance" />,
          reliabilityAction: (e) => <OverrideAssessmentPopover event={e} kind="reliability" />,
          edit: (e) =>
            editing ? (
              <EditEventForm event={e} onDone={() => setEditing(false)} />
            ) : (
              <UpdatesSinceEditBanner event={e} />
            ),
          history: (e) => <HistoryTab eventId={e.id} timeZone={me.timezone} />,
          brief: (e) => <BriefPanel event={e} />,
          draft: (e) => <DraftPanel event={e} timeZone={me.timezone} />,
        }}
        onClose={() => void navigate({ to: "/" })}
        onSelectEvent={(id) => void navigate({ to: "/events/$eventId", params: { eventId: id } })}
      />
    </div>
  );
}
