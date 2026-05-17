/*
 * Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The ASF licenses this file to You under the Apache License, Version 2.0
 * (the "License"); you may not use this file except in compliance with
 * the License.  You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.apache.commons.lang;

/**
 * <p>Operations on {@link java.lang.String} that are
 * <code>null</code> safe.</p>
 *
 * <p><strong>OMNIX test-corpus subset</strong> of Apache Commons Lang 2.6's
 * {@code org.apache.commons.lang.StringUtils}. Only {@code reverse(String)} is
 * retained, and its body's reference to the internal {@code StrBuilder} has
 * been replaced with {@code java.lang.StringBuilder} so this file is
 * parseable in isolation by the OMNIX JavaParser-based symbol solver without
 * vendoring the rest of Commons Lang. Functional contract is identical:
 * both return a reversed copy of the input or null on null input.</p>
 *
 * <p>See {@code tests/corpus/COMMONS_LANG_LICENSE.md} for full provenance,
 * Apache 2.0 attribution, and the rationale for trimming.</p>
 *
 * @see java.lang.String
 * @author Apache Software Foundation
 * @since 1.0 (upstream)
 */
public class StringUtils {

    /**
     * <p><code>StringUtils</code> instances should NOT be constructed in
     * standard programming. Instead, the class should be used as
     * <code>StringUtils.trim(" foo ");</code>.</p>
     *
     * <p>This constructor is public to permit tools that require a JavaBean
     * instance to operate.</p>
     */
    public StringUtils() {
        super();
    }

    /**
     * <p>Reverses a String as per {@link StringBuilder#reverse()}.</p>
     *
     * <p>A <code>null</code> String returns <code>null</code>.</p>
     *
     * <pre>
     * StringUtils.reverse(null)  = null
     * StringUtils.reverse("")    = ""
     * StringUtils.reverse("bat") = "tab"
     * </pre>
     *
     * @param str  the String to reverse, may be null
     * @return the reversed String, <code>null</code> if null String input
     */
    public static String reverse(String str) {
        if (str == null) {
            return null;
        }
        return new StringBuilder(str).reverse().toString();
    }

}
