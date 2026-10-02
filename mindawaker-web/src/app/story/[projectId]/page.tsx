import StoryEditor from '@/components/StoryEditor';

export default function StoryPage({ params }: { params: { projectId: string } }) {
  return <StoryEditor projectId={params.projectId} />;
}
