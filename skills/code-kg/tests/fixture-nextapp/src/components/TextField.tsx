interface TextFieldProps {
  label: string;
  name: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
  error?: string;
}

export function TextField({
  label,
  name,
  value,
  onChange,
  type = "text",
  placeholder,
  error,
}: TextFieldProps) {
  return (
    <label className="field" htmlFor={name}>
      <span className="field-label">{label}</span>
      <input
        id={name}
        name={name}
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
      {error ? <span className="field-error">{error}</span> : null}
    </label>
  );
}
