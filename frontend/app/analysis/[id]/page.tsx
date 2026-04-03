export default function AnalysisDetail({ params }: { params: { id: string } }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen w-full">
      <h1 className="text-4xl text-secondary font-bold mb-4">Analysis Results</h1>
      <p className="text-lg">Swarm consensus for run: {params.id}</p>
    </div>
  )
}
