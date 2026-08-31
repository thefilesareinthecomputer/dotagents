USER ASKED: "should we use Redis or Postgres for the job queue?"

ASSISTANT REPLIED (verbose):
This is a classic architectural decision, and both options have passionate
advocates in the engineering community. Let me give you a thorough comparison
so you can make an informed decision.

Redis is an in-memory data structure store that has become extremely popular
for queue workloads. Its advantages include exceptional throughput, often
exceeding 100,000 operations per second on modest hardware, native support for
list and stream data structures that map naturally onto queue semantics, and a
rich ecosystem of libraries like BullMQ and Sidekiq that provide
production-grade queue features out of the box. On the other hand, Redis brings
operational costs: it is another service to run, monitor, back up and secure,
and its persistence guarantees are weaker than a traditional database unless
you configure AOF fsync carefully, which costs throughput.

Postgres, meanwhile, has gained significant traction as a queue backend in
recent years, especially with the SKIP LOCKED feature introduced in 9.5. The
advantages here are compelling: you already run Postgres, so there is no new
infrastructure, jobs participate in the same transactions as your business
data, which eliminates an entire class of dual-write bugs, and durability is
inherited from your existing backup and replication setup. The main concern
people raise is throughput, but for queues processing fewer than a few thousand
jobs per minute, Postgres handles the load comfortably.

Considering that your application already uses Postgres, processes roughly 200
jobs per minute, and that your team is small with limited ops capacity, my
recommendation would lean toward Postgres with SKIP LOCKED, likely via a
library like Oban or River depending on your language. You avoid new
infrastructure, gain transactional job enqueueing, and 200 jobs per minute is
far below the threshold where Redis's throughput advantage would matter.

That said, if you anticipate 100x growth in queue volume or need sub-second
latency guarantees, Redis would be the more future-proof choice. Would you like
me to sketch out what the Postgres implementation would look like?
