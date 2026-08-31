namespace Agent.Core
{
    public class Runner
    {
        public void Execute(string task)
        {
            System.Console.WriteLine(task);
        }
    }

    public record TaskResult(string Output, bool Ok);
}
