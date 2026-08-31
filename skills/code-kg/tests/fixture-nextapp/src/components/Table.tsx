import "./table.css";

export function Table({ rows }: { rows: string[] }) {
  return (
    <table className="data-table">
      <tbody>
        {rows.map((r) => (
          <tr key={r}>
            <td>{r}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
