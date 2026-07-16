import { useEffect } from "react";
import { createPortal } from "react-dom";

export function ImageLightbox({
  src,
  alt,
  label,
  onClose,
}: {
  src: string;
  alt: string;
  label: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={label}
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute right-4 top-4 rounded-lg border border-white/20 bg-black/60 px-3 py-1.5 text-sm text-white transition hover:bg-black/80"
      >
        Chiudi
      </button>
      <div
        className="flex max-h-[92vh] max-w-[min(96vw,1200px)] flex-col items-center gap-3"
        onClick={(event) => event.stopPropagation()}
      >
        <p className="text-sm font-medium text-white/90">{label}</p>
        <img
          src={src}
          alt={alt}
          className="max-h-[calc(92vh-2.5rem)] w-auto max-w-full object-contain"
        />
      </div>
    </div>,
    document.body,
  );
}
