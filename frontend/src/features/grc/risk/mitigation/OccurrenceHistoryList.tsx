/**
 * Read-only audit list for a task's past occurrences.
 *
 * One line per cycle (including the currently-open one), showing
 * sequence number, status, due date, completion timestamp, who closed
 * it, and — critically — who was the task owner at the moment of
 * completion. That last snapshot is the audit trail the user asked
 * for, since the parent task's owner may have rotated since.
 */
import { useTranslation } from "react-i18next";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import MaterialSymbol from "@/components/MaterialSymbol";
import type { MitigationTaskOccurrence } from "@/types";

interface Props {
  occurrences: MitigationTaskOccurrence[];
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function OccurrenceHistoryList({ occurrences }: Props) {
  const { t } = useTranslation("delivery");

  if (occurrences.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {t("risks.tasks.history.empty")}
      </Typography>
    );
  }

  // Sort newest first so the latest cycle is at the top.
  const sorted = [...occurrences].sort((a, b) => b.sequence - a.sequence);

  return (
    <Stack spacing={1.5}>
      {sorted.map((occ) => {
        const isOpen = occ.status === "open";
        const icon =
          occ.status === "done"
            ? "check_circle"
            : occ.status === "skipped"
              ? "skip_next"
              : "schedule";
        const color =
          occ.status === "done"
            ? "success.main"
            : occ.status === "skipped"
              ? "warning.main"
              : "text.secondary";
        return (
          <Box
            key={occ.id}
            id={`occurrence-${occ.id}`}
            sx={{
              display: "flex",
              gap: 1.5,
              alignItems: "flex-start",
              p: 1,
              borderRadius: 1,
              border: 1,
              borderColor: "divider",
            }}
          >
            <Box sx={{ color, pt: 0.25 }}>
              <MaterialSymbol icon={icon} size={20} />
            </Box>
            <Stack spacing={0.25} sx={{ flex: 1, minWidth: 0 }}>
              <Stack direction="row" spacing={1} alignItems="baseline" flexWrap="wrap">
                <Typography variant="body2" fontWeight={600}>
                  {t("risks.tasks.history.cycleLabel", { sequence: occ.sequence })}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {t(`risks.tasks.status.${occ.status}`)}
                </Typography>
                {occ.due_date && (
                  <Typography variant="caption" color="text.secondary">
                    · {t("risks.tasks.history.dueOn", { date: occ.due_date })}
                  </Typography>
                )}
              </Stack>
              {isOpen ? (
                <Typography variant="caption" color="text.secondary">
                  {occ.assigned_owner_name
                    ? t("risks.tasks.history.assignedTo", {
                        name: occ.assigned_owner_name,
                      })
                    : t("risks.tasks.history.unassigned")}
                </Typography>
              ) : (
                <>
                  <Typography variant="caption" color="text.secondary">
                    {t("risks.tasks.history.closedAt", {
                      timestamp: formatDateTime(occ.completed_at),
                    })}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {t("risks.tasks.history.completedBy", {
                      name: occ.completed_by_name ?? "—",
                      owner: occ.owner_at_completion_name ?? "—",
                    })}
                  </Typography>
                </>
              )}
              {occ.completion_notes && (
                <Typography
                  variant="body2"
                  sx={{ mt: 0.5, whiteSpace: "pre-wrap", color: "text.primary" }}
                >
                  {occ.completion_notes}
                </Typography>
              )}
            </Stack>
          </Box>
        );
      })}
    </Stack>
  );
}
