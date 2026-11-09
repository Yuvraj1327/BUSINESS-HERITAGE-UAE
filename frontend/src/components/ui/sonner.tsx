import { Toaster as Sonner, type ToasterProps } from 'sonner'

/** Global toast host (light theme only in v1). Mounted once in App. */
function Toaster(props: ToasterProps) {
  return (
    <Sonner
      theme="light"
      position="top-right"
      richColors
      closeButton
      toastOptions={{ classNames: { toast: 'font-sans' } }}
      {...props}
    />
  )
}

export { Toaster }
