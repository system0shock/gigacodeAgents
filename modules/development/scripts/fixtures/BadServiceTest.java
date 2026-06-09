package com.example.fixtures;

import org.junit.Test;
import org.junit.Before;

// Deliberately violates the test checks: used as smoke-check input only.
public class BadServiceTest {

    @Before
    public void setUp() {
    }

    @Test
    public void test1() {
        new BadService().process("x");
    }
}
