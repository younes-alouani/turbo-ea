import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import LinearProgress from "@mui/material/LinearProgress";
import Typography from "@mui/material/Typography";
import { api } from "@/api/client";
import MaterialSymbol from "@/components/MaterialSymbol";
import StakeholderHoverCard from "@/components/StakeholderHoverCard";
import { useResolveLabel, useResolveMetaLabel } from "@/hooks/useResolveLabel";
import SectionPaper, { EmptyState } from "../workspace/SectionPaper";

interface DirectoryUser {
  user_id: string;
  display_name: string;
  email?: string;
  card_count: number;
}

interface DirectoryRole {
  role_key: string;
  role_label: string;
  role_color: string;
  role_translations: Record<string, string>;
  users: DirectoryUser[];
}

interface DirectoryCardType {
  type_key: string;
  type_label: string;
  type_icon: string;
  type_color: string;
  holders_count: number;
  roles: DirectoryRole[];
}

interface DirectoryResponse {
  card_types: DirectoryCardType[];
}

export default function StakeholderDirectorySection() {
  const { t } = useTranslation("common");
  const rl = useResolveLabel();
  const rml = useResolveMetaLabel();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<DirectoryResponse | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    api
      .get<DirectoryResponse>("/reports/stakeholder-directory")
      .then((res) => {
        if (cancelled) return;
        setData(res);
        // Pre-expand the first card type so the section isn't fully
        // collapsed by default — the user can see the structure at a
        // glance and click the others to drill in.
        if (res.card_types[0]) {
          setExpanded(new Set([res.card_types[0].type_key]));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleType = (typeKey: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(typeKey)) next.delete(typeKey);
      else next.add(typeKey);
      return next;
    });
  };

  return (
    <SectionPaper
      icon="groups_3"
      iconColor="#1976d2"
      title={t("dashboard.admin.stakeholderDirectory")}
    >
      {loading ? (
        <LinearProgress />
      ) : !data || data.card_types.length === 0 ? (
        <EmptyState message={t("dashboard.admin.stakeholderDirectory.empty")} />
      ) : (
        <Box>
          {data.card_types.map((ct) => {
            const isOpen = expanded.has(ct.type_key);
            return (
              <Box key={ct.type_key} sx={{ mb: 1, "&:last-of-type": { mb: 0 } }}>
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    gap: 1,
                    py: 0.75,
                    px: 1,
                    borderRadius: 1,
                    cursor: "pointer",
                    bgcolor: isOpen ? "action.hover" : "transparent",
                    "&:hover": { bgcolor: "action.hover" },
                  }}
                  onClick={() => toggleType(ct.type_key)}
                >
                  <IconButton size="small" sx={{ p: 0.25 }}>
                    <MaterialSymbol
                      icon={isOpen ? "expand_more" : "chevron_right"}
                      size={18}
                    />
                  </IconButton>
                  <MaterialSymbol icon={ct.type_icon} size={18} color={ct.type_color} />
                  <Typography variant="body2" sx={{ fontWeight: 600, flex: 1 }} noWrap>
                    {rml(ct.type_key, undefined, "label") || ct.type_label}
                  </Typography>
                  <Chip
                    size="small"
                    label={t("dashboard.admin.stakeholderDirectory.holdersCount", {
                      count: ct.holders_count,
                    })}
                    sx={{
                      height: 22,
                      fontSize: "0.7rem",
                      bgcolor: "background.paper",
                      border: 1,
                      borderColor: "divider",
                    }}
                  />
                </Box>
                {isOpen && (
                  <Box sx={{ pl: 4, pt: 0.5, pb: 1 }}>
                    {ct.roles.map((role) => (
                      <Box
                        key={role.role_key}
                        sx={{ mb: 1.25, "&:last-of-type": { mb: 0 } }}
                      >
                        <Box
                          sx={{
                            display: "flex",
                            alignItems: "center",
                            gap: 0.75,
                            mb: 0.5,
                          }}
                        >
                          <Box
                            sx={{
                              width: 8,
                              height: 8,
                              borderRadius: "50%",
                              bgcolor: role.role_color,
                              flexShrink: 0,
                            }}
                          />
                          <Typography
                            variant="caption"
                            sx={{
                              fontWeight: 600,
                              textTransform: "uppercase",
                              letterSpacing: 0.5,
                              fontSize: "0.7rem",
                              color: "text.secondary",
                            }}
                          >
                            {rl(role.role_label, role.role_translations)}
                          </Typography>
                        </Box>
                        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                          {role.users.map((u) => (
                            <StakeholderHoverCard
                              key={u.user_id}
                              userId={u.user_id}
                              userName={u.display_name}
                            >
                              <Chip
                                size="small"
                                label={
                                  <Box
                                    component="span"
                                    sx={{ display: "flex", alignItems: "baseline", gap: 0.5 }}
                                  >
                                    <Box component="span">{u.display_name}</Box>
                                    <Box
                                      component="span"
                                      sx={{
                                        fontSize: "0.65rem",
                                        opacity: 0.75,
                                      }}
                                    >
                                      ·{" "}
                                      {t(
                                        "dashboard.admin.stakeholderDirectory.cardsCount",
                                        { count: u.card_count },
                                      )}
                                    </Box>
                                  </Box>
                                }
                                sx={{
                                  height: 24,
                                  fontSize: "0.72rem",
                                  bgcolor: "background.paper",
                                  border: 1,
                                  borderColor: "divider",
                                  cursor: "default",
                                }}
                              />
                            </StakeholderHoverCard>
                          ))}
                        </Box>
                      </Box>
                    ))}
                  </Box>
                )}
              </Box>
            );
          })}
        </Box>
      )}
    </SectionPaper>
  );
}
