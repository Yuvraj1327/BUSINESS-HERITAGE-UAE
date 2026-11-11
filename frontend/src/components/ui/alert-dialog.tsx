import * as AlertPrimitive from '@radix-ui/react-alert-dialog'
import * as React from 'react'
import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const AlertDialog = AlertPrimitive.Root
const AlertDialogTrigger = AlertPrimitive.Trigger

function AlertDialogContent({
  className,
  ...props
}: React.ComponentProps<typeof AlertPrimitive.Content>) {
  return (
    <AlertPrimitive.Portal>
      <AlertPrimitive.Overlay className="fixed inset-0 z-50 bg-slate-950/50 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
      <AlertPrimitive.Content
        className={cn(
          'fixed top-1/2 left-1/2 z-50 grid w-full max-w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 gap-4 rounded-xl border bg-card p-6 shadow-pop data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0 sm:max-w-md',
          className,
        )}
        {...props}
      />
    </AlertPrimitive.Portal>
  )
}
function AlertDialogHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('flex flex-col gap-1.5 text-left', className)} {...props} />
}
function AlertDialogFooter({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn('flex flex-col-reverse gap-2 sm:flex-row sm:justify-end', className)}
      {...props}
    />
  )
}
function AlertDialogTitle({
  className,
  ...props
}: React.ComponentProps<typeof AlertPrimitive.Title>) {
  return <AlertPrimitive.Title className={cn('text-lg font-semibold', className)} {...props} />
}
function AlertDialogDescription({
  className,
  ...props
}: React.ComponentProps<typeof AlertPrimitive.Description>) {
  return (
    <AlertPrimitive.Description
      className={cn('text-sm text-muted-foreground', className)}
      {...props}
    />
  )
}
function AlertDialogAction({
  className,
  ...props
}: React.ComponentProps<typeof AlertPrimitive.Action>) {
  return <AlertPrimitive.Action className={cn(buttonVariants(), className)} {...props} />
}
function AlertDialogCancel({
  className,
  ...props
}: React.ComponentProps<typeof AlertPrimitive.Cancel>) {
  return (
    <AlertPrimitive.Cancel
      className={cn(buttonVariants({ variant: 'outline' }), className)}
      {...props}
    />
  )
}

export {
  AlertDialog,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
}
