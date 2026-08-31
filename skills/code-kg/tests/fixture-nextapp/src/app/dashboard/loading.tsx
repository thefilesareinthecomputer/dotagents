import { Spinner } from "@/components";

export default function DashboardLoading() {
  return (
    <div className="dashboard-loading">
      <Spinner label="Preparing dashboard" />
    </div>
  );
}
