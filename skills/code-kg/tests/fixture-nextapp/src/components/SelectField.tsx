interface Option {
  value: string;
  label: string;
}

interface SelectFieldProps {
  label: string;
  name: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
}

export function SelectField({ label, name, value, options, onChange }: SelectFieldProps) {
  return (
    <label className="field" htmlFor={name}>
      <span className="field-label">{label}</span>
      <select
        id={name}
        name={name}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}
