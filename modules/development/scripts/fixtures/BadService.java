package com.example.fixtures;

import java.util.*;

// Deliberately violates the static checks: used as smoke-check input only.
public class BadService {

    public void process(String input) {
        // TODO: handle null input
        try {
            System.out.println("processing " + input);
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
