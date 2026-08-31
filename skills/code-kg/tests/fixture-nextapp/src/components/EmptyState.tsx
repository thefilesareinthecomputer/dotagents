import { Button } from "./Button";

interface EmptyStateProps {
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({ title, description, actionLabel, onAction }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <h2>{title}</h2>
      {description ? <p>{description}</p> : null}
      {actionLabel && onAction ? (
        <Button label={actionLabel} onClick={onAction} />
      ) : null}
    </div>
  );
}
