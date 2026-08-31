package com.example.agent;

import com.example.agent.Tool;
import java.util.List;

public class Router {
    private final List<Tool> tools;

    public Router(List<Tool> tools) {
        this.tools = tools;
    }

    public static void main(String[] args) {
        System.out.println("router up");
    }
}
