using Agent.Core;

namespace Agent.App
{
    public class Program
    {
        static void Main(string[] args)
        {
            var runner = new Runner();
            runner.Execute("hello");
        }
    }
}
