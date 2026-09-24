/** Real wall-clock greeting - never a stand-in for a candidate/user name we don't have. */
export function timeOfDayGreeting(date: Date = new Date()): string {
  const hour = date.getHours()
  if (hour < 5) return "Working late"
  if (hour < 12) return "Good morning"
  if (hour < 18) return "Good afternoon"
  return "Good evening"
}
