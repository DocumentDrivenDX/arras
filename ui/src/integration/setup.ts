// SPDX-License-Identifier: MIT OR Apache-2.0
import { configure } from "@testing-library/react";

// Real HTTP is slower than the fetch double: wait longer for what the server answers.
configure({ asyncUtilTimeout: 8_000 });
