import Workspace from "@/components/Workspace";
export default async function EncounterPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <Workspace id={id} />;
}
