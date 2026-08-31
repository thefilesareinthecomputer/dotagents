package queue

type Queue struct {
	items []string
	cap   int
}

func New(capacity int) *Queue {
	return &Queue{cap: capacity}
}

func (q *Queue) Push(item string) {
	q.items = append(q.items, item)
}

func (q *Queue) Len() int {
	return len(q.items)
}
