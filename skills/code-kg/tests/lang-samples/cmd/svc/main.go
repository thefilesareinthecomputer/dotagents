package main

import (
	"fmt"

	"example.com/agentsvc/internal/queue"
)

type Config struct {
	Workers int
}

func main() {
	q := queue.New(4)
	q.Push("job-1")
	fmt.Println(q.Len())
}
