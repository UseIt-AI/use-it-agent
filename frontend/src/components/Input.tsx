export function Input(props: {
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  ref?: React.RefObject<HTMLInputElement>;
}) {
  return <input 
    className="w-full px-3 py-1.5 my-2 bg-white border border-divider text-sm text-black/90 placeholder-black/40 rounded focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/20"
    placeholder={props.placeholder}
    value={props.value}
    disabled={props.disabled}
    ref={props.ref}
    onChange={(e) => props.onChange?.(e.target.value)}
  />
}