import PortfolioReport from "./PortfolioReport";

/** Flexible Portfolio — same UX as the Application Portfolio with a card-type
 * picker at the top of the toolbar. Backed by the shared `PortfolioReport`
 * component so both reports stay in lockstep. */
export default function FlexiblePortfolioReport() {
  return (
    <PortfolioReport
      showTypeSelector
      savedReportKey="flexible-portfolio"
    />
  );
}
