export default function Dashboard() {
  return (
    <div className="flex flex-col items-start justify-start min-h-screen w-full p-12">
      <h1 className="text-4xl text-accent font-bold mb-6">Swarm Dashboard</h1>
      <div className="w-full grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-6 bg-surface border border-border rounded-lg shadow-sm">
          <h2 className="text-xl font-semibold mb-2">Total Datasets</h2>
          <p className="text-3xl text-primary font-bold">0</p>
        </div>
        <div className="p-6 bg-surface border border-border rounded-lg shadow-sm">
          <h2 className="text-xl font-semibold mb-2">Active Swarm Models</h2>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-accent animate-pulse"></span>
            <p className="text-3xl font-bold">0</p>
          </div>
        </div>
      </div>
    </div>
  )
}
