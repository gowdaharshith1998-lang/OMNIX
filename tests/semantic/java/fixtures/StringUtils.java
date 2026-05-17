package org.apache.commons.lang;

/**
 * Minimal Java 6 fixture for the OMNIX M1 retrocausal anchor.
 * Intentionally written in pre-Java-7 idioms: no var, no lambdas,
 * no streams, no diamond operator, no try-with-resources.
 */
public class StringUtils {

    private StringUtils() {
        // utility class
    }

    public static String reverse(String input) {
        if (input == null) {
            return null;
        }
        StringBuilder builder = new StringBuilder(input.length());
        for (int i = input.length() - 1; i >= 0; i--) {
            builder.append(input.charAt(i));
        }
        return builder.toString();
    }

    public static boolean isEmpty(String input) {
        return input == null || input.length() == 0;
    }

    public static boolean isBlank(String input) {
        if (isEmpty(input)) {
            return true;
        }
        for (int i = 0; i < input.length(); i++) {
            if (!Character.isWhitespace(input.charAt(i))) {
                return false;
            }
        }
        return true;
    }
}
